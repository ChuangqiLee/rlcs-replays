"""Controlled, scratch-trained player encoders; no pretrained-model claims.

Mamba/spatial masking follows the existing Sports-Traj (ICLR 2025) adaptation;
sLSTM/patch masking follows the existing TiRex (NeurIPS 2025) adaptation. Their
Transformer controls share input, spatial/patch stack and game aggregation.
"""
from __future__ import annotations

import math
import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from pilot_encoder.models import make_model as make_pilot
from pilot_encoder.models_v3 import BidirectionalTemporalMamba, UniTrajEncoder
from pilot_encoder.models_v4 import SLSTMBlock, TiRexEncoder, contiguous_patch_mask


def pooled_channels(x):
    """Recover the pilot's 38 pooled channels exactly from seven-agent tokens."""
    if x.ndim == 3 and x.shape[-1] == 38:
        return x
    if x.ndim != 4 or x.shape[-2:] != (7, 16):
        raise ValueError('Expected [B,T,7,16] agents or [B,T,38] pooled inputs')
    pieces = [x[:, :, 0, :15], x[:, :, 6, :6], x[:, :, 6, 15:16]]
    for start, stop in ((1, 3), (3, 6)):
        values = x[:, :, start:stop]
        available = values[..., 15:16]
        count = available.sum(2)
        means = (values[..., :7] * available).sum(2) / count.clamp_min(1)
        pieces.extend((means, count / (stop-start)))
    return torch.cat(pieces, dim=-1)


def _positions(length, width, tensor):
    position = torch.arange(length, device=tensor.device, dtype=tensor.dtype)[:, None]
    frequency = torch.exp(torch.arange(0, width, 2, device=tensor.device,
                                        dtype=tensor.dtype) * (-math.log(10000) / width))
    phase = position * frequency
    return torch.stack((phase.sin(), phase.cos()), dim=-1).flatten(1)


class WindowEncoder(nn.Module):
    """One controlled spatial/pooled front end and one temporal component."""
    def __init__(self, config):
        super().__init__()
        self.backbone = config.get('backbone', 'transformer')
        self.inputs = config.get('inputs', 'agents')
        self.masking = bool(config.get('masking', True))
        tiny = bool(config.get('tiny', False))
        width, layers, heads = (16, 1, 2) if tiny else (128, 2, 4)
        self.width = width
        self.pilot = None
        if self.backbone.startswith('pilot_'):
            variant = self.backbone[6:]
            if variant in ('v1', 'v2'):
                self.pilot = make_pilot(variant, 38, tiny=tiny)
            elif variant == 'v3':
                self.pilot = UniTrajEncoder(tiny=tiny)
            elif variant == 'v4':
                self.pilot = TiRexEncoder(tiny=tiny)
            else:
                raise ValueError('Unknown pilot backbone')
            self.width = 128
            return
        self.patch = self.backbone in ('slstm', 'patch_transformer')
        if self.inputs not in ('agents', 'pooled'):
            raise ValueError('inputs must be agents or pooled')
        if self.patch and self.inputs != 'pooled':
            raise ValueError('Patch controls require identical pooled inputs')
        if self.inputs == 'agents':
            self.input = nn.Linear(16, width)
            self.roles = nn.Embedding(4, width)
            self.ghost = nn.Parameter(torch.zeros(width))
            self.register_buffer('role_ids', torch.tensor([0, 1, 1, 2, 2, 2, 3]))
            layer = nn.TransformerEncoderLayer(width, heads, 2*width, .1,
                                               activation='gelu', batch_first=True, norm_first=True)
            self.spatial = nn.TransformerEncoder(layer, 1 if tiny else 2,
                                                  enable_nested_tensor=False)
        else:
            self.input = nn.Linear(38 * (6 if self.patch else 1), width)
        self.mask_token = nn.Parameter(torch.zeros(width)) if self.patch else None
        if self.backbone in ('transformer', 'patch_transformer'):
            layer = nn.TransformerEncoderLayer(width, heads, 2*width, .1,
                                               activation='gelu', batch_first=True, norm_first=True)
            self.temporal = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        elif self.backbone == 'gru':
            self.temporal = nn.GRU(width, width//2, layers, batch_first=True,
                                    bidirectional=True, dropout=.1 if layers > 1 else 0.)
        elif self.backbone == 'mamba':
            self.temporal = nn.ModuleList(BidirectionalTemporalMamba(width, 4 if tiny else 8,
                                                                     2 if tiny else 8)
                                          for _ in range(layers))
        elif self.backbone == 'slstm':
            self.temporal = nn.ModuleList(SLSTMBlock(width, heads, 2*width) for _ in range(layers))
        else:
            raise ValueError(f'Unknown backbone {self.backbone}')

    def forward(self, x, mask):
        if mask.shape != x.shape[:2] or not bool(mask.any(1).all()):
            raise ValueError('Every window needs at least one valid frame')
        if self.pilot is not None:
            return self.pilot(x if self.backbone == 'pilot_v3' else pooled_channels(x), mask)
        if self.inputs == 'agents':
            if x.ndim != 4 or x.shape[2:] != (7, 16):
                raise ValueError('Agent stack requires seven 16-channel tokens')
            x = x.masked_fill(~mask[..., None, None], 0)
            available = x[..., 15] > 0
            ghost = ~available
            if self.training and self.masking:
                sampled = torch.rand_like(available, dtype=x.dtype) < .15
                sampled[..., 0] = False
                ghost = ghost | (sampled & available)
            tokens = torch.where(ghost[..., None], self.ghost, self.input(x))
            tokens = tokens + self.roles(self.role_ids)
            hidden = self.spatial(tokens.flatten(0, 1))[:, 0].reshape(*mask.shape, self.width)
        else:
            x = pooled_channels(x).masked_fill(~mask[..., None], 0)
            if self.patch:
                padding = (-x.shape[1]) % 6
                x = F.pad(x, (0, 0, 0, padding))
                mask = F.pad(mask, (0, padding), value=False)
                x = x.reshape(x.shape[0], -1, 6*38)
                mask = mask.reshape(mask.shape[0], -1, 6).any(-1)
            hidden = self.input(x)
            if self.patch and self.training and self.masking:
                hidden, _ = contiguous_patch_mask(hidden, mask, self.mask_token)
        # Positions shared within each paired temporal comparison, including Mamba.
        hidden = (hidden + _positions(hidden.shape[1], self.width, hidden)[None])
        hidden = hidden.masked_fill(~mask[..., None], 0)
        if self.backbone in ('transformer', 'patch_transformer'):
            hidden = self.temporal(hidden, src_key_padding_mask=~mask)
        elif self.backbone == 'gru':
            packed = pack_padded_sequence(hidden, mask.sum(1).cpu(), batch_first=True,
                                          enforce_sorted=False)
            packed, _ = self.temporal(packed)
            hidden, _ = pad_packed_sequence(packed, batch_first=True, total_length=mask.shape[1])
        else:
            for block in self.temporal:
                hidden = block(hidden, mask)
        return (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)


class GameEncoder(nn.Module):
    """Encode only existing windows, then aggregate one equal-weight player-game."""
    def __init__(self, config):
        super().__init__()
        self.window_encoder = WindowEncoder(config)
        width = self.window_encoder.width
        self.pooling = config.get('pooling', 'meanstd')
        if self.pooling not in ('mean', 'meanstd', 'attention'):
            raise ValueError('pooling must be mean, meanstd or attention')
        if self.pooling == 'attention':
            self.attention = nn.Sequential(nn.Linear(width, width//2), nn.Tanh(), nn.Linear(width//2, 1))
        self.output = nn.Linear(width if self.pooling == 'mean' else 2*width, 128)
        self.existing_pilot = config.get('backbone', '').startswith('pilot_')
        if self.existing_pilot:
            self.output = nn.Identity()
            if self.pooling != 'mean':
                raise ValueError('Existing pilots retain equal-window mean aggregation')

    def aggregate(self, values, valid):
        if not bool(valid.any(1).all()):
            raise ValueError('Every player-game needs at least one window')
        if self.pooling == 'attention':
            logits = self.attention(values).squeeze(-1).masked_fill(~valid, -torch.inf)
            weights = logits.softmax(1)
        else:
            weights = valid.to(values.dtype) / valid.sum(1, keepdim=True)
        mean = (values * weights[..., None]).sum(1)
        if self.pooling != 'mean':
            variance = ((values - mean[:, None]).square() * weights[..., None]).sum(1)
            # Epsilon prevents the derivative of sqrt(0) for single-window games.
            std = (variance + 1e-8).sqrt()
            mean = torch.cat((mean, std), -1)
        return F.normalize(self.output(mean), dim=-1)

    def forward(self, x, masks, bag_mask=None, return_windows=False):
        if bag_mask is None:
            bag_mask = masks.any(-1)
        if x.shape[:3] != masks.shape or x.shape[:2] != bag_mask.shape:
            raise ValueError('Expected x[B,K,T,...], masks[B,K,T], bag_mask[B,K]')
        flat_valid = bag_mask.flatten()
        values = self.window_encoder(x.flatten(0, 1)[flat_valid], masks.flatten(0, 1)[flat_valid])
        padded = values.new_zeros((*bag_mask.shape, values.shape[-1]))
        padded[bag_mask] = values
        game = self.aggregate(padded, bag_mask)
        if return_windows:
            singleton = self.aggregate(values[:, None], torch.ones((len(values), 1),
                                                                   dtype=torch.bool, device=x.device))
            return game, singleton
        return game


def make_model(config):
    return GameEncoder(config)
