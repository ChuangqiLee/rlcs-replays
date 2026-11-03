"""Player-fingerprint encoder with identity and contrastive objectives.

Architecture (default): per-frame role-aware spatial attention over the seven
agent tokens (query car, two teammates, three opponents, ball), a temporal
encoder over the 60-frame query stream, a linear head to a 128-d unit-norm
window embedding, and equal-weight averaging of window embeddings into a game
embedding. Supervision uses the training identities only: a cosine identity
classifier on window and game embeddings (optionally with an additive angular
margin) and a supervised contrastive term between the two games of each
identity in a batch. No identity, roster, season or series information enters
the encoder inputs.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F

from pilot_encoder.models_v3 import BidirectionalTemporalMamba
from .models import _positions, pooled_channels


def chunked(module, x, chunk=32768):
    """Apply a per-sequence module in chunks; large flattened frame batches exceed CUDA grid limits."""
    if x.shape[0] <= chunk:
        return module(x)
    return torch.cat([module(x[i:i + chunk]) for i in range(0, x.shape[0], chunk)], 0)


class Standardizer(nn.Module):
    """Per-channel affine normalization fitted on TRAIN windows only."""
    def __init__(self, mean, std):
        super().__init__()
        self.register_buffer('mean', torch.as_tensor(mean, dtype=torch.float32))
        self.register_buffer('std', torch.as_tensor(std, dtype=torch.float32))

    def forward(self, x):
        return (x - self.mean) / self.std

    @staticmethod
    def fit(values, masks, available=None, floor=1e-3):
        """values[N,T,...], masks[N,T]; channels with tiny spread keep scale one."""
        valid = values[masks]
        mean = valid.mean(0)
        std = valid.std(0)
        std = torch.where(std < floor, torch.ones_like(std), std)
        mean = torch.where(std == 1., torch.zeros_like(mean), mean) if available is None else mean
        return mean, std


class FingerprintEncoder(nn.Module):
    def __init__(self, cfg, standardizer=None):
        super().__init__()
        d, heads = int(cfg['width']), int(cfg['heads'])
        drop = float(cfg.get('dropout', .1))
        self.inputs = cfg.get('inputs', 'agents')
        self.temporal_kind = cfg.get('temporal', 'transformer')
        self.ghost_prob = float(cfg.get('ghost_prob', .15))
        self.emb = int(cfg.get('embedding', 128))
        self.width = d
        self.pos_scale = float(cfg.get('pos_scale', .1))
        self.standardizer = standardizer
        self.use_std = bool(cfg.get('standardize', True)) and standardizer is not None
        if self.inputs == 'agents':
            self.input = nn.Linear(16, d)
            self.roles = nn.Embedding(4, d)
            # Small role vectors keep tokens input-dominated instead of constant-dominated.
            nn.init.normal_(self.roles.weight, std=float(cfg.get('role_init', .02)))
            self.ghost = nn.Parameter(torch.zeros(d))
            self.register_buffer('role_ids', torch.tensor([0, 1, 1, 2, 2, 2, 3]), persistent=False)
            layer = nn.TransformerEncoderLayer(d, heads, 2 * d, drop, activation='gelu',
                                               batch_first=True, norm_first=True)
            self.spatial = nn.TransformerEncoder(layer, int(cfg.get('spatial_layers', 2)),
                                                 enable_nested_tensor=False)
            self.context = bool(cfg.get('context_token', True))
            self.merge = nn.Linear(2 * d, d) if self.context else None
        elif self.inputs == 'pooled':
            self.input = nn.Linear(38, d)
        else:
            raise ValueError('inputs must be agents or pooled')
        layers = int(cfg.get('temporal_layers', 2))
        if self.temporal_kind == 'transformer':
            layer = nn.TransformerEncoderLayer(d, heads, 2 * d, drop, activation='gelu',
                                               batch_first=True, norm_first=True)
            self.temporal = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        elif self.temporal_kind == 'gru':
            self.temporal = nn.GRU(d, d // 2, layers, batch_first=True, bidirectional=True,
                                   dropout=drop if layers > 1 else 0.)
        elif self.temporal_kind == 'mamba':
            self.temporal = nn.ModuleList(BidirectionalTemporalMamba(d, 8, 8) for _ in range(layers))
        else:
            raise ValueError('temporal must be transformer, gru or mamba')
        self.norm = nn.LayerNorm(d)
        self.head = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, self.emb))
        # BNNeck (Luo et al. 2019): batch statistics remove the shared offset of
        # the pre-normalized embedding so identity differences are not swamped.
        self.bnneck = nn.BatchNorm1d(self.emb) if bool(cfg.get('bnneck', True)) else None
        # Game-level aggregation: mean (default) or mean+SD of window embeddings,
        # optionally concatenated with exact mean/SD statistics of the standardized
        # raw input channels over all frames of the game (a residual on top of the
        # information-matched summary baseline).
        self.game_pool = cfg.get('game_pool', 'mean')
        self.raw_skip = bool(cfg.get('raw_skip', False)) and self.inputs == 'agents'
        self.raw_dim = 7 * 16
        in_dim = self.emb * (2 if self.game_pool == 'meanstd' else 1) + (2 * self.raw_dim if self.raw_skip else 0)
        self.projected_games = self.game_pool != 'mean' or self.raw_skip
        self.game_proj = nn.Linear(in_dim, self.emb) if self.projected_games else None
        self.game_bn = nn.BatchNorm1d(self.emb) if self.projected_games and self.bnneck is not None else None

    def frame_tokens(self, x, mask):
        """x[B,T,7,16] raw physical scaling -> query stream [B,T,d]."""
        available = x[..., 15] > 0
        if self.use_std:
            x = self.standardizer(x)
        x = x.masked_fill(~mask[..., None, None], 0)
        ghost = ~available
        if self.training and self.ghost_prob > 0:
            sampled = torch.rand_like(available, dtype=x.dtype) < self.ghost_prob
            sampled[..., 0] = False
            ghost = ghost | (sampled & available)
        tokens = torch.where(ghost[..., None], self.ghost.to(x.dtype), self.input(x))
        tokens = tokens + self.roles(self.role_ids)
        b, t = mask.shape
        out = chunked(self.spatial, tokens.flatten(0, 1))
        query = out[:, 0]
        if self.context:
            others = out[:, 1:].mean(1)
            query = self.merge(torch.cat((query, others), -1))
        return query.reshape(b, t, self.width)

    def raw_stats(self, x, mask):
        """Per-window sums of standardized raw channels over valid frames: (sum, sum of squares, count)."""
        if self.use_std:
            x = self.standardizer(x)
        x = x.masked_fill(~mask[..., None, None], 0).flatten(2)
        return x.sum(1), x.square().sum(1), mask.sum(1).to(x.dtype)

    def window_embeddings(self, x, mask, return_stats=False):
        """Return unit-norm window embeddings [N, emb] (and raw statistics when requested)."""
        if mask.shape != x.shape[:2] or not bool(mask.any(1).all()):
            raise ValueError('Every window needs at least one valid frame')
        stats = self.raw_stats(x, mask) if (return_stats and self.inputs == 'agents') else None
        if self.inputs == 'agents':
            hidden = self.frame_tokens(x, mask)
        else:
            p = pooled_channels(x)
            if self.use_std:
                p = self.standardizer(p)
            hidden = self.input(p.masked_fill(~mask[..., None], 0))
        hidden = hidden + self.pos_scale * _positions(hidden.shape[1], self.width, hidden)[None]
        hidden = hidden.masked_fill(~mask[..., None], 0)
        if self.temporal_kind == 'transformer':
            hidden = self.temporal(hidden, src_key_padding_mask=~mask)
        elif self.temporal_kind == 'gru':
            lengths = mask.sum(1).cpu()
            packed = nn.utils.rnn.pack_padded_sequence(hidden, lengths, batch_first=True, enforce_sorted=False)
            packed, _ = self.temporal(packed)
            hidden, _ = nn.utils.rnn.pad_packed_sequence(packed, batch_first=True, total_length=mask.shape[1])
        else:
            for block in self.temporal:
                hidden = block(hidden, mask)
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        z = self.head(self.norm(pooled))
        if self.bnneck is not None:
            z = self.bnneck(z)
        z = F.normalize(z, dim=-1)
        return (z, stats) if return_stats else z

    def game_sums(self, z, bag_index, n_games, stats=None):
        """Accumulate per-game sums needed by ``finalize`` (usable across chunks)."""
        zsum = z.new_zeros((n_games, z.shape[-1])).index_add_(0, bag_index, z)
        zsq = z.new_zeros((n_games, z.shape[-1])).index_add_(0, bag_index, z.square())
        nw = z.new_zeros(n_games).index_add_(0, bag_index, torch.ones(len(z), device=z.device, dtype=z.dtype))
        if stats is None:
            return zsum, zsq, nw, None, None, None
        xsum, xsq, nf = stats
        return (zsum, zsq, nw, z.new_zeros((n_games, xsum.shape[-1])).index_add_(0, bag_index, xsum.to(z.dtype)),
                z.new_zeros((n_games, xsq.shape[-1])).index_add_(0, bag_index, xsq.to(z.dtype)),
                z.new_zeros(n_games).index_add_(0, bag_index, nf.to(z.dtype)))

    def finalize(self, zsum, zsq, nw, xsum=None, xsq=None, nf=None):
        """Game embedding from accumulated sums."""
        nw = nw.clamp_min(1)[:, None]
        mean = zsum / nw
        if not self.projected_games:
            return F.normalize(mean, dim=-1)
        parts = [mean]
        if self.game_pool == 'meanstd':
            parts.append((zsq / nw - mean.square()).clamp_min(1e-8).sqrt())
        if self.raw_skip:
            if xsum is None:
                raise ValueError('raw_skip needs raw statistics')
            nf = nf.clamp_min(1)[:, None]
            rm = xsum / nf
            parts += [rm, (xsq / nf - rm.square()).clamp_min(1e-8).sqrt()]
        g = self.game_proj(torch.cat(parts, -1))
        if self.game_bn is not None:
            g = self.game_bn(g)
        return F.normalize(g, dim=-1)

    def game_embeddings(self, z, bag_index, n_games, stats=None):
        """Game embeddings for one batch of windows."""
        return self.finalize(*self.game_sums(z, bag_index, n_games, stats))


class CosineClassifier(nn.Module):
    """Normalized-prototype softmax with optional additive angular margin (ArcFace)."""
    def __init__(self, emb, n_classes, scale=16., margin=0.):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(n_classes, emb))
        nn.init.xavier_uniform_(self.weight)
        self.scale, self.margin = float(scale), float(margin)

    def forward(self, z, labels=None):
        cosine = F.linear(z, F.normalize(self.weight, dim=-1)).clamp(-1 + 1e-6, 1 - 1e-6)
        if labels is None or self.margin <= 0 or not self.training:
            return self.scale * cosine
        theta = torch.acos(cosine.gather(1, labels[:, None]))
        target = torch.cos(theta + self.margin)
        return self.scale * cosine.scatter(1, labels[:, None], target)


def supcon(z, labels, temperature=.1):
    self_pair = torch.eye(len(z), device=z.device, dtype=torch.bool)
    positive = labels[:, None].eq(labels[None, :]) & ~self_pair
    counts = positive.sum(1)
    logits = (z @ z.T) / temperature
    log_prob = logits - torch.logsumexp(logits.masked_fill(self_pair, -torch.inf), dim=1)[:, None]
    keep = counts > 0
    return -(log_prob.masked_fill(~positive, 0).sum(1)[keep] / counts[keep]).mean()


class FingerprintModel(nn.Module):
    """Encoder plus training heads; only the encoder is used at retrieval time."""
    def __init__(self, cfg, n_identities, standardizer=None):
        super().__init__()
        self.cfg = dict(cfg)
        self.encoder = FingerprintEncoder(cfg, standardizer)
        self.classifier = CosineClassifier(self.encoder.emb, n_identities,
                                           float(cfg.get('scale', 16.)), float(cfg.get('margin', 0.)))
        self.game_classifier = (CosineClassifier(self.encoder.emb, n_identities, float(cfg.get('scale', 16.)),
                                                 float(cfg.get('margin', 0.)))
                                if self.encoder.projected_games else self.classifier)
        self.w_window = float(cfg.get('w_window_ce', 1.))
        self.w_game = float(cfg.get('w_game_ce', 1.))
        self.w_supcon = float(cfg.get('w_supcon', 0.))
        self.temperature = float(cfg.get('temperature', .1))

    def forward(self, x, mask, bag_index, n_games, window_labels, game_labels):
        z, stats = self.encoder.window_embeddings(x, mask, return_stats=True)
        g = self.encoder.game_embeddings(z, bag_index, n_games, stats)
        terms = {}
        if self.w_window > 0:
            terms['window_ce'] = F.cross_entropy(self.classifier(z, window_labels), window_labels)
        if self.w_game > 0:
            terms['game_ce'] = F.cross_entropy(self.game_classifier(g, game_labels), game_labels)
        if self.w_supcon > 0:
            terms['supcon'] = supcon(g, game_labels, self.temperature)
        loss = (self.w_window * terms.get('window_ce', 0.) + self.w_game * terms.get('game_ce', 0.)
                + self.w_supcon * terms.get('supcon', 0.))
        with torch.no_grad():
            if 'window_ce' in terms:
                terms['window_acc'] = (self.classifier(z).argmax(1) == window_labels).float().mean()
            terms['game_acc'] = (self.game_classifier(g).argmax(1) == game_labels).float().mean()
        return loss, {k: float(v) for k, v in terms.items()}, g
