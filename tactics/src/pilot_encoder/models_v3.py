"""Preregistered UniTraj adaptation, isolated from the V1/V2 model factory.

The diagonal selective state update is an inclusive associative scan in pure
PyTorch. Its custom reverse scan saves only transitions and resulting states,
rather than the O(log T) intermediate autograd graphs of the parallel scan.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


def _affine_scan(transition: torch.Tensor, value: torch.Tensor) -> torch.Tensor:
    """Inclusive prefix of h[t] = transition[t] * h[t-1] + value[t]."""
    state, product = value, transition
    stride = 1
    while stride < value.shape[1]:
        state = torch.cat((state[:, :stride],
                           state[:, stride:] + product[:, stride:] * state[:, :-stride]), dim=1)
        if stride * 2 < value.shape[1]:
            product = torch.cat((product[:, :stride],
                                 product[:, stride:] * product[:, :-stride]), dim=1)
        stride *= 2
    return state


class _SelectiveScan(torch.autograd.Function):
    @staticmethod
    def forward(ctx, log_transition, value):
        transition = log_transition.exp()
        state = _affine_scan(transition, value)
        ctx.save_for_backward(transition, state)
        return state

    @staticmethod
    def backward(ctx, grad_state):
        transition, state = ctx.saved_tensors
        # dL/dh[t] = direct[t] + transition[t+1] * dL/dh[t+1].
        next_transition = torch.cat((transition[:, 1:], torch.zeros_like(transition[:, :1])), dim=1)
        adjoint = _affine_scan(next_transition.flip(1), grad_state.flip(1)).flip(1)
        previous_state = torch.cat((torch.zeros_like(state[:, :1]), state[:, :-1]), dim=1)
        return adjoint * previous_state * transition, adjoint


def selective_scan(log_transition: torch.Tensor, value: torch.Tensor) -> torch.Tensor:
    """Stable parallel scan of nonpositive log transitions, with zero initial state.

    Both inputs are [batch,time,width,state]. No division, inverse cumulative
    products or exp of positive transition sums are used, including padding.
    """
    if log_transition.shape != value.shape or value.ndim != 4 or value.shape[1] < 1:
        raise ValueError('Selective scan expects matching nonempty [B,T,D,S] tensors')
    return _SelectiveScan.apply(log_transition, value)


class RMSNorm(nn.Module):
    def __init__(self, width: int):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))

    def forward(self, x):
        return x * torch.rsqrt(x.square().mean(dim=-1, keepdim=True) + 1e-5) * self.weight


def reverse_valid_prefix(x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Reverse live prefix independently for each sample; leave padding at end."""
    positions = torch.arange(x.shape[1], device=x.device)[None].expand(x.shape[:2])
    lengths = mask.sum(dim=1, keepdim=True)
    source = torch.where(positions < lengths, lengths - 1 - positions, positions)
    return x.gather(1, source.unsqueeze(-1).expand_as(x))


class SelectiveMamba(nn.Module):
    def __init__(self, width: int, state_size: int, dt_rank: int):
        super().__init__()
        self.state_size, self.dt_rank = state_size, dt_rank
        self.input = nn.Linear(width, 2 * width, bias=False)
        self.convolution = nn.Conv1d(width, width, kernel_size=4, padding=3, groups=width)
        self.select = nn.Linear(width, dt_rank + 2 * state_size, bias=False)
        self.dt = nn.Linear(dt_rank, width)
        nn.init.constant_(self.dt.bias, math.log(math.expm1(0.1)))
        self.A_log = nn.Parameter(torch.arange(1, state_size + 1, dtype=torch.float32)
                                  .log().repeat(width, 1))
        self.D = nn.Parameter(torch.ones(width))
        self.output = nn.Linear(width, width, bias=False)

    def forward(self, x, mask):
        x = x.masked_fill(~mask[..., None], 0)
        content, gate = self.input(x).chunk(2, dim=-1)
        content = F.silu(self.convolution(content.transpose(1, 2))[:, :, :x.shape[1]].transpose(1, 2))
        content = content.masked_fill(~mask[..., None], 0)
        dt_low, b, c = self.select(content).split([self.dt_rank, self.state_size, self.state_size], dim=-1)
        dt = F.softplus(self.dt(dt_low))
        log_transition = -dt[..., None] * self.A_log.exp()
        log_transition = log_transition.masked_fill(~mask[..., None, None], 0)
        value = dt[..., None] * b[:, :, None, :] * content[..., None]
        value = value.masked_fill(~mask[..., None, None], 0)
        state = selective_scan(log_transition, value)
        y = (state * c[:, :, None, :]).sum(dim=-1) + self.D * content
        return self.output(y * F.silu(gate)).masked_fill(~mask[..., None], 0)


class BidirectionalTemporalMamba(nn.Module):
    def __init__(self, width: int, state_size: int, dt_rank: int):
        super().__init__()
        self.norm = RMSNorm(width)
        self.forward_core = SelectiveMamba(width, state_size, dt_rank)
        self.backward_core = SelectiveMamba(width, state_size, dt_rank)
        self.fusion = nn.Linear(2 * width, width, bias=False)
        self.ffn_norm = RMSNorm(width)
        self.ffn = nn.Sequential(nn.Linear(width, 2 * width), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(2 * width, width), nn.Dropout(0.1))

    def forward(self, x, mask):
        normalized = self.norm(x)
        forward = self.forward_core(normalized, mask)
        backward = reverse_valid_prefix(self.backward_core(reverse_valid_prefix(normalized, mask), mask), mask)
        x = x + self.fusion(torch.cat((forward, backward), dim=-1))
        return (x + self.ffn(self.ffn_norm(x))).masked_fill(~mask[..., None], 0)


class UniTrajEncoder(nn.Module):
    """Seven-agent spatial Transformer followed by a query-stream temporal BTM."""

    def __init__(self, input_dim: int = 16, tiny: bool = False):
        super().__init__()
        if input_dim != 16:
            raise ValueError('V3 requires exactly 16 channels per agent')
        width, spatial_layers, heads, temporal_layers, state_size, dt_rank = (
            (16, 1, 2, 1, 4, 2) if tiny else (128, 2, 4, 4, 8, 8))
        self.input = nn.Linear(input_dim, width)
        self.roles = nn.Embedding(4, width)
        self.ghost = nn.Parameter(torch.zeros(width))
        self.register_buffer('role_ids', torch.tensor([0, 1, 1, 2, 2, 2, 3]), persistent=False)
        spatial = nn.TransformerEncoderLayer(width, heads, 2 * width, dropout=0.1,
                                              activation='gelu', batch_first=True, norm_first=True)
        self.spatial = nn.TransformerEncoder(spatial, spatial_layers, enable_nested_tensor=False)
        self.temporal = nn.ModuleList([BidirectionalTemporalMamba(width, state_size, dt_rank)
                                       for _ in range(temporal_layers)])
        self.output = nn.Linear(width, 128)

    def agent_tokens(self, x, mask):
        """Ghost masking retains role but never masks the available focal car."""
        x = x.masked_fill(~mask[..., None, None], 0)
        available = x[..., -1] > 0
        ghost = ~available
        if self.training:
            sampled = torch.rand(available.shape, device=x.device) < 0.15
            sampled[..., 0] = False
            ghost = ghost | (sampled & available)
        token = torch.where(ghost[..., None], self.ghost, self.input(x))
        return token + self.roles(self.role_ids)

    def forward(self, x, mask):
        if x.ndim != 4 or x.shape[2:] != (7, 16) or mask.shape != x.shape[:2]:
            raise ValueError('V3 expects x[B,T,7,16], mask[B,T]')
        batch, frames = x.shape[:2]
        token = self.agent_tokens(x, mask)
        # All seven tokens participate, including learned ghosts for missing agents.
        query = self.spatial(token.reshape(batch * frames, 7, -1))[:, 0]
        query = query.reshape(batch, frames, -1).masked_fill(~mask[..., None], 0)
        for block in self.temporal:
            query = block(query, mask)
        weight = mask[..., None].to(query.dtype)
        pooled = (query * weight).sum(dim=1) / weight.sum(dim=1).clamp_min(1)
        return F.normalize(self.output(pooled), dim=-1)


def make_model(input_dim: int = 16, tiny: bool = False) -> nn.Module:
    return UniTrajEncoder(input_dim=input_dim, tiny=tiny)
