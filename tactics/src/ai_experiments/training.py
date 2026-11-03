"""Train-only game sampling, operational caps and last-iterate fitting."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from pilot_encoder.dataset import assert_allowed
from pilot_encoder.models import supervised_contrastive_loss
from pilot_encoder.training import seed_everything
from tactics_code.screen import TRAIN_SEASONS
from .models import make_model


class TrainingGateError(RuntimeError):
    def __init__(self, report):
        super().__init__('Train-only tiny-batch overfit gate failed; expansion stopped')
        self.report = report


class GameSampler:
    """Uniform train identities, two distinct games, preferring different series.

    The co-occurring and random-extra conditions add exactly the same number
    of identities for each base draw. Random mode first computes the available
    co-occurrence count, then draws that many uniformly from remaining IDs.
    """
    def __init__(self, dataset, batch_identities=8, seed=42, extra_negatives='none'):
        games = dataset.games.reset_index(drop=True)
        assert_allowed(games)
        train = games[games.split == 'train']
        if not set(train.season) <= set(TRAIN_SEASONS):
            raise ValueError('Training games must be strictly pre-2025')
        self.rng = np.random.default_rng(seed)
        self.extra_rng = np.random.default_rng(seed+100003)
        self.extra_negatives = extra_negatives
        if extra_negatives not in ('none', 'random', 'cooccurring'):
            raise ValueError('Unknown extra-negative condition')
        self.by_identity = {str(identity): group.index.to_numpy()
                            for identity, group in train.groupby('identity_id', sort=True)
                            if len(group) >= 2}
        self.identities = sorted(self.by_identity)
        self.dropped_single_game_ids = int(train.identity_id.nunique() - len(self.identities))
        if len(self.identities) < 2:
            raise ValueError('At least two training identities with distinct games required')
        self.batch_identities = min(int(batch_identities), len(self.identities))
        if self.batch_identities < 2:
            raise ValueError('At least two identities per contrastive batch required')
        self.games = games
        self.series = games.series_id.astype(str).to_numpy()
        self.replays = games.replay_id.astype(str).to_numpy()
        self.replay_identities = {str(replay): sorted(set(group.identity_id.astype(str)) & set(self.identities))
                                  for replay, group in train.groupby('replay_id')}
        self.windows = [[] for _ in range(len(games))]
        for index, game in enumerate(np.asarray(dataset.window_games)):
            if not 0 <= game < len(games):
                raise ValueError('Window references an unknown game')
            self.windows[int(game)].append(index)
        if any(not self.windows[i] for ids in self.by_identity.values() for i in ids):
            raise ValueError('A training game has no windows')
        self.train_games = sum(map(len, self.by_identity.values()))
        self.steps_per_epoch = math.ceil(self.train_games / (2*self.batch_identities))
        self.same_series_pairs = self.cross_series_pairs = self.extra_identities = 0

    def _pair(self, identity, first=None, rng=None):
        rng = self.rng if rng is None else rng
        available = self.by_identity[identity]
        first = int(rng.choice(available)) if first is None else int(first)
        others = available[available != first]
        different = others[self.series[others] != self.series[first]]
        second = int(rng.choice(different if len(different) else others))
        if self.series[first] == self.series[second]:
            self.same_series_pairs += 1
        else:
            self.cross_series_pairs += 1
        return [first, second]

    def sample(self):
        chosen = self.rng.choice(self.identities, self.batch_identities, replace=False).tolist()
        pairs = [self._pair(identity) for identity in chosen]
        if self.extra_negatives != 'none':
            used, cooccurring = set(chosen), []
            for pair in pairs:
                anchor = int(self.rng.choice(pair))
                candidates = [identity for identity in self.replay_identities[self.replays[anchor]]
                              if identity not in used]
                if candidates:
                    identity = str(self.rng.choice(candidates))
                    cooccurring.append((identity, self.replays[anchor]))
                    used.add(identity)
            if self.extra_negatives == 'random':
                remaining = [identity for identity in self.identities if identity not in chosen]
                extras = [(str(identity), None) for identity in self.extra_rng.choice(
                    remaining, len(cooccurring), replace=False)]
            else:
                extras = cooccurring
            for identity, replay in extras:
                available = self.by_identity[identity]
                first = None if replay is None else int(self.extra_rng.choice(available[self.replays[available] == replay]))
                pairs.append(self._pair(identity, first, rng=self.extra_rng))
                chosen.append(identity)
            self.extra_identities += len(extras)
        indices = np.asarray(pairs).reshape(-1)
        labels = np.repeat([self.identities.index(identity) for identity in chosen], 2)
        return indices, labels

    def report(self):
        return {'train_identities': len(self.identities), 'train_games': self.train_games,
                'dropped_single_game_identities': self.dropped_single_game_ids,
                'same_series_positive_pairs': self.same_series_pairs,
                'cross_series_positive_pairs': self.cross_series_pairs,
                'extra_identities': self.extra_identities,
                'extra_negatives': self.extra_negatives}


def _array(dataset, config):
    pooled = config.get('inputs') == 'pooled' or config.get('backbone') in ('pilot_v1', 'pilot_v2', 'pilot_v4')
    if pooled and hasattr(dataset, 'pooled_x'):
        return dataset.pooled_x
    if pooled and dataset.x.ndim == 4:
        raise ValueError('Pooled experiments require exact dataset.pooled_x channels')
    return dataset.x


def make_batch(dataset, windows, game_indices, config, device, cap=None):
    values = _array(dataset, config)
    selected = [windows[int(game)][:cap] if cap else windows[int(game)] for game in game_indices]
    width = max(map(len, selected))
    if not width or any(not row for row in selected):
        raise ValueError('Every requested game requires a window')
    x = np.zeros((len(selected), width, *values.shape[1:]), dtype=np.float32)
    masks = np.zeros((len(selected), width, values.shape[1]), dtype=np.bool_)
    bag = np.zeros((len(selected), width), dtype=np.bool_)
    for i, row in enumerate(selected):
        x[i, :len(row)] = values[row]
        masks[i, :len(row)] = dataset.masks[row]
        bag[i, :len(row)] = True
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite model input')
    return tuple(torch.as_tensor(item, device=device) for item in (x, masks, bag))


def embedding_diagnostics(z, labels):
    """Training-only collapse measurements; not proof of their cause."""
    z = np.asarray(z, dtype=np.float64)
    centered = z-z.mean(0)
    singular = np.linalg.svd(centered, compute_uv=False)
    energy = singular**2
    probability = energy / max(float(energy.sum()), 1e-30)
    positive = probability > 0
    rank = float(np.exp(-(probability[positive]*np.log(probability[positive])).sum())) if positive.any() else 0.
    distance = 1-z@z.T
    same = np.asarray(labels)[:, None] == np.asarray(labels)[None, :]
    np.fill_diagonal(same, False)
    different = np.asarray(labels)[:, None] != np.asarray(labels)[None, :]
    return {'mean_feature_variance': float(centered.var(0).mean()), 'effective_rank': rank,
            'same_identity_cosine_distance': float(distance[same].mean()) if same.any() else None,
            'different_identity_cosine_distance': float(distance[different].mean()) if different.any() else None}


def _loss(model, batch, labels, objective):
    x, masks, bag = batch
    if objective == 'window':
        _, z = model(x, masks, bag, return_windows=True)
        labels = labels[:, None].expand_as(bag)[bag]
    elif objective == 'game':
        z = model(x, masks, bag)
    else:
        raise ValueError('objective must be window or game')
    return supervised_contrastive_loss(z, labels, .1), z


def _diagnostic_partition(sampler, config):
    """Reserve complete TRAIN series before choosing the tiny overfit games."""
    series = sorted(set(sampler.series[np.concatenate(list(sampler.by_identity.values()))]))
    seed = int(config.get('selection_seed', 42))
    heldout = {s for s in series if int(hashlib.sha256(f'{seed}:{s}'.encode()).hexdigest()[:8], 16) % 5 == 0}
    partitions = [heldout] + [{series[-1]}] if series else []
    for reserve in partitions:
        supported = []
        for identity, indices in sampler.by_identity.items():
            is_heldout = np.isin(sampler.series[indices], list(reserve))
            if (~is_heldout).sum() >= 2 and is_heldout.any():
                supported.append(identity)
        if len(supported) < 2:
            continue
        rng = np.random.default_rng(seed)
        identities = rng.choice(sorted(supported), 2, replace=False).tolist()
        fit_indices, query_indices, query_labels = [], [], []
        for identity in identities:
            indices = sampler.by_identity[identity]
            heldout_indices = indices[np.isin(sampler.series[indices], list(reserve))]
            fitting = indices[~np.isin(sampler.series[indices], list(reserve))]
            first = int(rng.choice(fitting))
            others = fitting[fitting != first]
            disjoint = others[sampler.series[others] != sampler.series[first]]
            second = int(rng.choice(disjoint if len(disjoint) else others))
            fit_indices.extend([first, second])
            # Bounded held-out diagnostic; no eligibility or scientific retrieval claim.
            selected = np.sort(heldout_indices)[:8].tolist()
            query_indices.extend(selected)
            query_labels.extend([sampler.identities.index(identity)]*len(selected))
        labels = np.repeat([sampler.identities.index(identity) for identity in identities], 2)
        return np.asarray(fit_indices), labels, np.asarray(query_indices), np.asarray(query_labels)
    indices, labels = sampler.sample()
    return indices, labels, np.asarray([], dtype=int), np.asarray([], dtype=int)


def _heldout_report(model, dataset, sampler, indices, labels, queries, query_labels,
                    batch, config, device):
    if not len(queries):
        return {'status': 'unavailable', 'reason': 'Fewer than two identities have two fitting games '
                'and another game in a disjoint reserved TRAIN series', 'fit_split': 'train'}
    fit_series = set(sampler.series[indices])
    query_series = set(sampler.series[queries])
    if fit_series & query_series:
        raise AssertionError('Diagnostic fit and heldout series overlap')
    with torch.no_grad():
        fitting = model(*batch).cpu().numpy()
        query = model(*make_batch(dataset, sampler.windows, queries, config, device, cap=2)).cpu().numpy()
    identities = np.unique(labels)
    gallery = np.stack([fitting[labels == identity].mean(0) for identity in identities])
    gallery /= np.maximum(np.linalg.norm(gallery, axis=1, keepdims=True), 1e-12)
    similarity = query @ gallery.T
    contributions = []
    for row, identity in zip(similarity, query_labels):
        target = int(np.flatnonzero(identities == identity)[0])
        better = int((row > row[target]+1e-10).sum())
        tied = int((np.abs(row-row[target]) <= 1e-10).sum())
        ranks = np.arange(better+1, better+tied+1)
        contributions.append([(ranks == 1).mean(), (ranks <= 5).mean(), (1/ranks).mean()])
    return {'status': 'available', 'fit_split': 'train', 'n_gallery': len(identities),
            'queries': len(query), 'fit_game_indices': indices.tolist(),
            'query_game_indices': queries.tolist(), 'fit_series': sorted(fit_series),
            'query_series': sorted(query_series), 'series_disjoint': True,
            'query_geometry': embedding_diagnostics(query, query_labels),
            'retrieval': dict(zip(('top1', 'top5', 'mrr'), np.mean(contributions, axis=0).tolist())),
            'claim': 'Tiny diagnostic only; not RQ4 eligibility; not used for stopping or selection'}


def _train_without_dropout(model):
    """Keep cuDNN recurrent backward enabled without stochastic dropout."""
    model.train()
    for module in model.modules():
        if isinstance(module, nn.modules.dropout._DropoutNd):
            module.eval()
        # Includes RNN/GRU/LSTM, transformer attention and custom probabilities.
        for name, value in vars(module).items():
            if 'dropout' in name and isinstance(value, (int, float)):
                setattr(module, name, 0.)


def train_only_gate(dataset, config, device='cpu', deadline=None):
    """Memorize a fixed tiny training batch with an independent fresh model."""
    seed_everything(int(config.get('seed', 42)))
    gate_config = dict(config, batch_identities=2, extra_negatives='none', masking=False)
    sampler = GameSampler(dataset, 2, int(config.get('seed', 42)))
    indices, labels, query_indices, query_labels = _diagnostic_partition(sampler, config)
    batch = make_batch(dataset, sampler.windows, indices, gate_config, device, cap=2)
    labels_numpy = labels.copy()
    labels = torch.as_tensor(labels, device=device)
    model = make_model(gate_config).to(device)
    _train_without_dropout(model)
    if gate_config.get('backbone') in ('pilot_v3', 'pilot_v4'):
        # These containers gate augmentation on training alone; keep their
        # descendants in training mode for backward, with dropout disabled.
        model.window_encoder.pilot.training = False
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=0.)
    initial_weights = torch.cat([p.detach().flatten().cpu() for p in model.parameters()])
    initial, z = _loss(model, batch, labels, config.get('objective', 'game'))
    before = embedding_diagnostics(z.detach().cpu().numpy(),
                                  labels[:, None].expand_as(batch[2])[batch[2]].cpu().numpy()
                                  if config.get('objective') == 'window' else labels.cpu().numpy())
    steps = int(config.get('diagnostic_steps', 100))
    maximum_gradient = 0.
    completed = 0
    for _ in range(steps):
        if deadline is not None and time.monotonic() >= deadline:
            break
        optimizer.zero_grad(set_to_none=True)
        loss, _ = _loss(model, batch, labels, config.get('objective', 'game'))
        if not torch.isfinite(loss):
            break
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        if not torch.isfinite(norm):
            break
        maximum_gradient = max(maximum_gradient, float(norm))
        optimizer.step()
        completed += 1
    model.eval()
    with torch.no_grad():
        final, final_z = _loss(model, batch, labels, config.get('objective', 'game'))
    delta = float(torch.linalg.vector_norm(torch.cat([p.detach().flatten().cpu() for p in model.parameters()])-initial_weights))
    expanded_labels = labels[:, None].expand_as(batch[2])[batch[2]] if config.get('objective') == 'window' else labels
    positives = (expanded_labels[:, None] == expanded_labels[None, :]).sum(1)-1
    floor = float(positives.float().log().mean())
    initial_value, final_value = float(initial.detach()), float(final)
    improved = (final_value-floor <= .8*max(initial_value-floor, 0.)) or final_value <= floor+.02
    passed = bool(steps == 0 or (completed == steps and torch.isfinite(final)
                  and improved and maximum_gradient > 0 and delta > 0))
    return {'passed': passed, 'disabled': steps == 0, 'steps': completed,
            'initial_loss': float(initial.detach()), 'final_loss': float(final),
            'equal_logit_loss': math.log(len(final_z)-1), 'max_gradient_norm': maximum_gradient,
            'supcon_positive_count_floor': floor,
            'parameter_delta_l2': delta, 'before': before,
            'after': embedding_diagnostics(final_z.cpu().numpy(), expanded_labels.cpu().numpy()),
            'disjoint_train_series': _heldout_report(model, dataset, sampler, indices, labels_numpy,
                query_indices, query_labels, batch, gate_config, device),
            'game_indices': indices.tolist(), 'fit_split': 'train', 'test_opened': False}


def _sync(device):
    if torch.device(device).type == 'cuda':
        torch.cuda.synchronize(device)


def _final_training_diagnostics(model, dataset, config, device):
    """Inspect the fitted model on a fresh seeded TRAIN draw, with no fitting."""
    sampler = GameSampler(dataset, 16, int(config.get('seed', 42))+900001, 'none')
    indices, labels_np = sampler.sample()
    labels = torch.as_tensor(labels_np, device=device)
    batch = make_batch(dataset, sampler.windows, indices, config, device)
    model.eval()
    with torch.no_grad():
        loss, z = _loss(model, batch, labels, config.get('objective', 'game'))
    if config.get('objective') == 'window':
        labels = labels[:, None].expand_as(batch[2])[batch[2]]
    positives = (labels[:, None] == labels[None, :]).sum(1)-1
    result = embedding_diagnostics(z.cpu().numpy(), labels.cpu().numpy())
    result.update(loss=float(loss), equal_logit_loss=math.log(len(z)-1),
                  supcon_positive_count_floor=float(positives.float().log().mean()),
                  anchors=len(z), game_indices=indices.tolist(),
                  fit_split='train', seed=int(config.get('seed', 42))+900001,
                  model_mode='eval; post-fit; no updates; no validation reads')
    return result


def _pretrain(model, dataset, sampler, config, optimizer, device, deadline):
    """History-only future focal-position MSE; complete-window targets only."""
    requested = int(config.get('pretrain_steps', config.get('pretraining_steps', 0)))
    if requested <= 0:
        return {'requested_steps': 0, 'steps': 0}
    head = nn.Linear(model.window_encoder.width, 3).to(device)
    pre_optimizer = torch.optim.AdamW(list(model.window_encoder.parameters()) + list(head.parameters()),
                                      lr=3e-4, weight_decay=1e-4)
    losses, skipped = [], 0
    for _ in range(requested):
        if time.monotonic() >= deadline:
            break
        games, _ = sampler.sample()
        x, masks, bag = make_batch(dataset, sampler.windows, games, config, device)
        x, masks = x.flatten(0, 1)[bag.flatten()], masks.flatten(0, 1)[bag.flatten()]
        complete = masks.all(1)
        if not bool(complete.any()):
            skipped += 1
            continue
        x = x[complete]
        midpoint = x.shape[1]//2
        if midpoint < 1:
            raise ValueError('Trajectory pretraining needs at least two frames')
        target = x[:, -1, 0, :3] if x.ndim == 4 else x[:, -1, :3]
        history = x[:, :midpoint]
        history_mask = torch.ones(history.shape[:2], dtype=torch.bool, device=device)
        pre_optimizer.zero_grad(set_to_none=True)
        prediction = head(model.window_encoder(history, history_mask))
        loss = F.mse_loss(prediction, target)
        if not bool(torch.isfinite(loss)):
            raise FloatingPointError('Nonfinite trajectory pretraining loss')
        loss.backward()
        nn.utils.clip_grad_norm_(list(model.window_encoder.parameters()) + list(head.parameters()), 1.)
        pre_optimizer.step()
        losses.append(float(loss.detach()))
    return {'requested_steps': requested, 'steps': len(losses), 'skipped_no_full_window': skipped,
            'mean_loss': float(np.mean(losses)) if losses else None,
            'target': 'last-frame focal xyz; first-half history only; physical units scaled',
            'head_discarded': True}


def fit(dataset, config, checkpoint_dir, device='cpu'):
    """No validation feature reads, model selection or metric-dependent stopping."""
    seed_everything(int(config.get('seed', 42)))
    device = torch.device(device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    objective = config.get('objective', 'game')
    if objective == 'window' and config.get('pooling', 'meanstd') != 'mean':
        raise ValueError('Window/game objective control requires the common mean projection')
    started = time.monotonic()
    budget = float(config.get('train_budget_seconds', 2400))
    deadline = started + budget
    sampler = GameSampler(dataset, config.get('batch_identities', 8), int(config.get('seed', 42)),
                          config.get('extra_negatives', 'none'))
    gate = None
    if not config.get('frozen', False):
        gate = train_only_gate(dataset, config, device, deadline)
        if not gate['passed'] and config.get('enforce_gate', True):
            raise TrainingGateError({'gate_passed': False, 'diagnostics': gate,
                                     'fit_seconds': time.monotonic()-started})
    seed_everything(int(config.get('seed', 42)))
    model = make_model(config).to(device)
    initial_parameters = torch.cat([p.detach().flatten().cpu() for p in model.parameters()])
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    pretraining = _pretrain(model, dataset, sampler, config, optimizer, device, deadline)
    epochs = int(config.get('epochs', 5))
    maximum = min(int(config.get('max_steps', 10000)), epochs*sampler.steps_per_epoch)
    if epochs < 1 or maximum < 1 or budget <= 0:
        raise ValueError('Positive epochs, steps and budget required')
    history, step_seconds = [], []
    windows_seen = games_seen = 0
    stop_reason = 'completed'
    model.train()
    if not config.get('frozen', False):
        for step in range(maximum):
            allowance = max(step_seconds[-20:], default=0.)*1.25
            if time.monotonic()+allowance >= deadline:
                stop_reason = 'time_budget'
                break
            step_start = time.monotonic()
            indices, labels = sampler.sample()
            batch = make_batch(dataset, sampler.windows, indices, config, device)
            labels = torch.as_tensor(labels, device=device)
            optimizer.zero_grad(set_to_none=True)
            loss, z = _loss(model, batch, labels, objective)
            if not bool(torch.isfinite(loss)):
                raise FloatingPointError('Nonfinite identity loss')
            loss.backward()
            gradient = nn.utils.clip_grad_norm_(model.parameters(), 1.)
            if not bool(torch.isfinite(gradient)):
                raise FloatingPointError('Nonfinite gradient')
            optimizer.step()
            _sync(device)
            step_seconds.append(time.monotonic()-step_start)
            history.append({'step': step+1, 'loss': float(loss.detach()),
                            'gradient_norm': float(gradient), 'anchors': len(z)})
            windows_seen += int(batch[2].sum())
            games_seen += len(indices)
        if len(history) == maximum and maximum < epochs*sampler.steps_per_epoch:
            stop_reason = 'step_cap'
        if not history:
            raise RuntimeError('Training budget expired before any identity update')
    else:
        stop_reason = 'frozen_random'
    model.eval()
    final_training_diagnostics = _final_training_diagnostics(model, dataset, config, device)
    final_parameters = torch.cat([p.detach().flatten().cpu() for p in model.parameters()])
    parameter_delta = float(torch.linalg.vector_norm(final_parameters-initial_parameters))
    destination = Path(checkpoint_dir)
    destination.mkdir(parents=True, exist_ok=True)
    checkpoint = destination/'last.pt'
    torch.save({'state_dict': model.state_dict(), 'config': dict(config), 'test_opened': False,
                'selection': 'last iterate', 'optimizer_steps': len(history)}, checkpoint)
    report = {'gate_passed': gate is None or gate['passed'], 'gate_enforced': config.get('enforce_gate', True),
              'diagnostics': gate, 'pretraining': pretraining,
              'final_train_diagnostics': final_training_diagnostics,
              'parameter_delta_l2': parameter_delta,
              'optimizer_steps': len(history), 'completed_epochs': len(history)//sampler.steps_per_epoch,
              'steps_per_epoch': sampler.steps_per_epoch, 'requested_epochs': epochs,
              'stop_reason': stop_reason, 'sampled_windows': windows_seen, 'sampled_games': games_seen,
              'fit_seconds': time.monotonic()-started, 'train_budget_seconds': budget,
              'parameters': sum(p.numel() for p in model.parameters()), 'sampler': sampler.report(),
              'history': history, 'checkpoint': str(checkpoint), 'fit_split': 'train',
              'train_seasons': list(TRAIN_SEASONS), 'test_opened': False,
              'selection': 'last iterate; no validation metric used',
              'optimizer': {'name': 'AdamW', 'lr': 3e-4, 'weight_decay': 1e-4,
                            'clip': 1., 'temperature': .1}}
    return model, report


def run_diagnostic(dataset, config, device='cpu'):
    """Public standalone train-only gate, independent of the subsequent fit."""
    seed_everything(int(config.get('seed', 42)))
    return train_only_gate(dataset, config, device,
                           time.monotonic()+float(config.get('train_budget_seconds', 2400)))


def embed_games(model, dataset, device='cpu', batch_size=8, config=None):
    """One vector per game, independent of how many padded windows it contains."""
    if config is None:
        config = {'inputs': model.window_encoder.inputs, 'backbone': model.window_encoder.backbone}
    assert_allowed(dataset.games)
    windows = [[] for _ in range(len(dataset.games))]
    for index, game in enumerate(dataset.window_games):
        windows[int(game)].append(index)
    model.eval()
    embeddings = []
    with torch.inference_mode():
        for start in range(0, len(windows), batch_size):
            indices = np.arange(start, min(start+batch_size, len(windows)))
            batch = make_batch(dataset, windows, indices, config, device)
            embeddings.append(model(*batch).cpu().numpy())
    result = np.concatenate(embeddings)
    if not np.isfinite(result).all():
        raise FloatingPointError('Nonfinite game embeddings')
    return result
