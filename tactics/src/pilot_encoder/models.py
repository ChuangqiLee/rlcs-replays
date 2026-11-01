"""Fixed player encoders for the preregistered pilot (no identity input)."""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


def _masked_mean(x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weight = mask.unsqueeze(-1).to(x.dtype)
    return (x * weight).sum(dim=1) / weight.sum(dim=1).clamp_min(1)


class TransformerEncoder(nn.Module):
    """Sinusoidal position, bidirectional attention, masked temporal mean."""

    def __init__(self, input_dim: int, tiny: bool = False):
        super().__init__()
        width, layers, heads, feedforward = (16, 1, 2, 32) if tiny else (128, 4, 4, 512)
        self.input = nn.Linear(input_dim, width)
        layer = nn.TransformerEncoderLayer(
            width, heads, feedforward, dropout=0.1, activation='gelu',
            batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.output = nn.Linear(width, 128)
        self.width = width

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        position = torch.arange(x.shape[1], device=x.device, dtype=x.dtype)[:, None]
        frequency = torch.exp(torch.arange(0, self.width, 2, device=x.device,
                                           dtype=x.dtype) * (-math.log(10000) / self.width))
        phase = position * frequency
        positional = torch.stack((phase.sin(), phase.cos()), dim=-1).flatten(1)
        hidden = self.encoder(self.input(x) + positional[None], src_key_padding_mask=~mask)
        return F.normalize(self.output(_masked_mean(hidden, mask)), dim=-1)


class BiGRUEncoder(nn.Module):
    """Three bidirectional layers, packed sequences, masked temporal mean."""

    def __init__(self, input_dim: int, tiny: bool = False):
        super().__init__()
        hidden = 8 if tiny else 64
        self.encoder = nn.GRU(input_dim, hidden, num_layers=3, bidirectional=True,
                              batch_first=True, dropout=0.1)
        self.output = nn.Linear(2 * hidden, 128)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        lengths = mask.sum(dim=1).cpu()
        packed = pack_padded_sequence(x, lengths, batch_first=True, enforce_sorted=False)
        hidden, _ = self.encoder(packed)
        hidden, _ = pad_packed_sequence(hidden, batch_first=True, total_length=x.shape[1])
        return F.normalize(self.output(_masked_mean(hidden, mask)), dim=-1)


def make_model(variant: str, input_dim: int, tiny: bool = False) -> nn.Module:
    """V1 = fixed Transformer; V2 = fixed three-layer bidirectional GRU."""
    if variant.lower() == 'v1':
        return TransformerEncoder(input_dim, tiny=tiny)
    if variant.lower() == 'v2':
        return BiGRUEncoder(input_dim, tiny=tiny)
    raise ValueError(f'Unknown pilot variant: {variant!r}; expected v1 or v2')


def supervised_contrastive_loss(embedding: torch.Tensor, labels: torch.Tensor,
                                 temperature: float = 0.1) -> torch.Tensor:
    """SupCon: all same-player windows are positives, excluding self pairs."""
    if temperature <= 0:
        raise ValueError('Temperature must be positive')
    self_pair = torch.eye(len(embedding), device=embedding.device, dtype=torch.bool)
    positive = labels[:, None].eq(labels[None, :]) & ~self_pair
    counts = positive.sum(dim=1)
    if not bool((counts > 0).all()):
        raise ValueError('Every contrastive anchor needs another same-identity window')
    logits = (embedding @ embedding.T) / temperature
    log_prob = logits - torch.logsumexp(logits.masked_fill(self_pair, -torch.inf), dim=1)[:, None]
    return -(log_prob.masked_fill(~positive, 0).sum(dim=1) / counts).mean()
