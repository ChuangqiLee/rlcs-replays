"""Preregistered TiRex/xLSTM adaptation; independent of the V1/V2 encoders.

This is a small, trained-from-scratch sLSTM encoder, not a TiRex checkpoint or a
forecasting-model reproduction. Exponential gates follow the equations fixed in
the 2026-11-01 addendum. All operations use ordinary PyTorch.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


class RMSNorm(nn.Module):
    def __init__(self, width: int):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.square().mean(dim=-1, keepdim=True) + 1e-5) * self.weight


def slstm_scan(gates: torch.Tensor, recurrent: torch.Tensor,
               mask: torch.Tensor) -> torch.Tensor:
    """Stabilized scalar-memory recurrence over the short patch sequence.

    ``gates`` is [B,T,4,D], ordered z/i/f/o. ``recurrent`` is
    [heads,4,head_width,head_width], so heads cannot mix recurrent states.
    Input projections are already batched over time; the ten recurrent steps
    have no Python loop over samples, heads or channels.
    """
    batch, steps, _, width = gates.shape
    heads, _, head_width, _ = recurrent.shape
    if width != heads * head_width or mask.shape != (batch, steps):
        raise ValueError('sLSTM gate, recurrent-head and temporal-mask shapes disagree')
    h = gates.new_zeros((batch, width))
    c, n, m = torch.zeros_like(h), torch.zeros_like(h), torch.zeros_like(h)
    outputs = []
    for step in range(steps):
        feedback = torch.einsum('bhj,hgij->bghi', h.reshape(batch, heads, head_width),
                                recurrent).reshape(batch, 4, width)
        z, i, f, o = (gates[:, step] + feedback).unbind(dim=1)
        next_m = torch.maximum(f + m, i)
        input_gate = torch.exp(i - next_m)
        forget_gate = torch.exp(f + m - next_m)
        next_c = forget_gate * c + input_gate * torch.tanh(z)
        next_n = forget_gate * n + input_gate
        next_h = torch.sigmoid(o) * next_c / next_n.clamp_min(1e-6)
        valid = mask[:, step, None]
        h = torch.where(valid, next_h, h)
        c = torch.where(valid, next_c, c)
        n = torch.where(valid, next_n, n)
        m = torch.where(valid, next_m, m)
        outputs.append(torch.where(valid, h, torch.zeros_like(h)))
    return torch.stack(outputs, dim=1)


def contiguous_patch_mask(contents: torch.Tensor, valid: torch.Tensor,
                          token: torch.Tensor, probability: float = 0.5):
    """Mask one contiguous span, preserving at least one observed valid patch.

    Called only in training. Returning the selected positions makes augmentation
    coverage directly testable without altering the model's public output.
    """
    lengths = valid.sum(dim=1)
    span = (lengths - 1).clamp(min=0, max=2)
    selected = (torch.rand(len(contents), device=contents.device) < probability) & (span > 0)
    starts = (torch.rand(len(contents), device=contents.device) *
              (lengths - span + 1).clamp_min(1)).floor().long()
    positions = torch.arange(contents.shape[1], device=contents.device)[None]
    hidden = selected[:, None] & (positions >= starts[:, None])
    hidden = hidden & (positions < (starts + span)[:, None]) & valid
    return torch.where(hidden[..., None], token, contents), hidden


class SLSTMBlock(nn.Module):
    def __init__(self, width: int, heads: int, feedforward: int):
        super().__init__()
        self.norm = RMSNorm(width)
        self.conv = nn.Conv1d(width, width, kernel_size=4, groups=width, padding=3)
        self.gates = nn.Linear(width, 4 * width)
        head_width = width // heads
        self.recurrent = nn.Parameter(torch.empty(heads, 4, head_width, head_width))
        nn.init.uniform_(self.recurrent, -1 / math.sqrt(head_width), 1 / math.sqrt(head_width))
        self.output = nn.Linear(width, width)
        self.ffnorm = RMSNorm(width)
        self.feedforward = nn.Sequential(nn.Linear(width, feedforward), nn.GELU(),
                                         nn.Dropout(0.1), nn.Linear(feedforward, width),
                                         nn.Dropout(0.1))

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        normalized = self.norm(x).masked_fill(~mask[..., None], 0)
        local = F.silu(self.conv(normalized.transpose(1, 2))[..., :x.shape[1]]).transpose(1, 2)
        gates = self.gates(local).reshape(x.shape[0], x.shape[1], 4, x.shape[2])
        hidden = slstm_scan(gates, self.recurrent, mask)
        x = (x + self.output(hidden)).masked_fill(~mask[..., None], 0)
        return (x + self.feedforward(self.ffnorm(x))).masked_fill(~mask[..., None], 0)


class TiRexEncoder(nn.Module):
    """Six-frame patches, stabilized sLSTM blocks, and contrastive projection."""

    def __init__(self, input_dim: int = 38, tiny: bool = False):
        super().__init__()
        if input_dim != 38:
            raise ValueError('V4 requires the frozen 38-channel query-player features')
        self.patch_size = 6
        self.width = 16 if tiny else 128
        layers, heads, feedforward = (1, 2, 32) if tiny else (4, 4, 256)
        self.input = nn.Linear(self.patch_size * input_dim, self.width)
        self.patch_mask_token = nn.Parameter(torch.zeros(self.width))
        self.blocks = nn.ModuleList(SLSTMBlock(self.width, heads, feedforward)
                                    for _ in range(layers))
        self.output = nn.Linear(self.width, 128)

    def patchify(self, x: torch.Tensor, mask: torch.Tensor):
        if x.ndim != 3 or x.shape[-1] != 38 or mask.shape != x.shape[:2]:
            raise ValueError('Expected V4 x[B,T,38] and mask[B,T]')
        x = x.masked_fill(~mask[..., None], 0)
        pad = (-x.shape[1]) % self.patch_size
        if pad:
            x = F.pad(x, (0, 0, 0, pad))
            mask = F.pad(mask, (0, pad), value=False)
        patches = x.reshape(x.shape[0], -1, self.patch_size * x.shape[-1])
        valid = mask.reshape(mask.shape[0], -1, self.patch_size).any(dim=-1)
        return patches, valid

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        patches, valid = self.patchify(x, mask)
        hidden = self.input(patches)
        if self.training:
            hidden, _ = contiguous_patch_mask(hidden, valid, self.patch_mask_token)
        position = torch.arange(hidden.shape[1], device=x.device, dtype=x.dtype)[:, None]
        frequency = torch.exp(torch.arange(0, self.width, 2, device=x.device, dtype=x.dtype)
                              * (-math.log(10000) / self.width))
        phase = position * frequency
        positional = torch.stack((phase.sin(), phase.cos()), dim=-1).flatten(1)
        hidden = (hidden + positional[None]).masked_fill(~valid[..., None], 0)
        for block in self.blocks:
            hidden = block(hidden, valid)
        weight = valid[..., None].to(hidden.dtype)
        pooled = (hidden * weight).sum(dim=1) / weight.sum(dim=1).clamp_min(1)
        return F.normalize(self.output(pooled), dim=-1)


def make_model(input_dim: int = 38, tiny: bool = False) -> TiRexEncoder:
    return TiRexEncoder(input_dim=input_dim, tiny=tiny)
