"""Train-only, identity-balanced SupCon fitting and synthetic throughput timing."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS
from tactics_code.style_retrieval import check_rows

from .diagnostics import batch_diagnostics
from .models import make_model, supervised_contrastive_loss


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    # Device/library differences can still change floating-point rounding.
    torch.use_deterministic_algorithms(True, warn_only=True)


def _sync(device: torch.device) -> None:
    if device.type == 'cuda':
        torch.cuda.synchronize(device)


def checkpoint_destination(path: Path) -> Path:
    """Checkpoints can only be written into explicit scratch or pilot artifacts."""
    target = Path(path).resolve()
    permitted = [(Path(__file__).resolve().parents[2] / 'artifacts' / 'pilot_encoder').resolve()]
    if os.environ.get('TMPDIR'):
        scratch = Path(os.environ['TMPDIR']).resolve()
        if scratch == Path('/'):
            raise ValueError('TMPDIR must not be the filesystem root')
        permitted.append(scratch)
    if not any(target == root or root in target.parents for root in permitted):
        raise ValueError('Checkpoints must be below $TMPDIR or artifacts/pilot_encoder/')
    target.mkdir(parents=True, exist_ok=True)
    return target


class IdentitySampler:
    """Uniform identities, uniform games, then uniform windows within each game."""

    def __init__(self, window_games, games, batch_identities=16, windows_per_identity=4, seed=42):
        check_rows(games)
        assert set(games.season) <= set(ALLOWED_SEASONS), '2026/test is forbidden'
        assert not games.season.astype(str).str.contains('2026').any(), '2026 must never be opened'
        if windows_per_identity < 2 or batch_identities < 2:
            raise ValueError('SupCon needs >=2 identities and >=2 windows per identity')
        self.rng = np.random.default_rng(seed)
        self.windows_per_identity = int(windows_per_identity)
        self.by_identity = {}
        window_games = np.asarray(window_games)
        if np.any(window_games < 0) or np.any(window_games >= len(games)):
            raise ValueError('Window game index outside games table')
        train_indices = np.flatnonzero(games.split.to_numpy() == 'train')
        check_rows(games.iloc[train_indices], 'train')
        assert set(games.iloc[train_indices].season) <= set(TRAIN_SEASONS)
        train_set = set(train_indices.tolist())
        windows_by_game = {}
        for window_index, game_index in enumerate(window_games):
            if int(game_index) in train_set:
                windows_by_game.setdefault(int(game_index), []).append(window_index)
        for game_index, indices in windows_by_game.items():
            identity = str(games.iloc[game_index].identity_id)
            self.by_identity.setdefault(identity, {})[game_index] = np.asarray(indices, dtype=np.int64)
        self.identities = sorted(self.by_identity)
        if len(self.identities) < 2:
            raise ValueError('At least two train identities with windows required')
        self.batch_identities = min(int(batch_identities), len(self.identities))
        self.train_windows = sum(len(indices) for indices in windows_by_game.values())
        self.batch_size = self.batch_identities * self.windows_per_identity
        self.steps_per_epoch = math.ceil(self.train_windows / self.batch_size)
        self.single_game_identities = sum(len(bag) < 2 for bag in self.by_identity.values())

    def sample(self):
        chosen = self.rng.choice(len(self.identities), size=self.batch_identities, replace=False)
        indices, labels = [], []
        for label in chosen:
            bag = self.by_identity[self.identities[int(label)]]
            game_indices = np.asarray(sorted(bag))
            # Repeated shuffled cycles guarantee multiple games whenever available.
            chosen_games = []
            while len(chosen_games) < self.windows_per_identity:
                chosen_games.extend(self.rng.permutation(game_indices).tolist())
            for game in chosen_games[:self.windows_per_identity]:
                indices.append(int(self.rng.choice(bag[game])))
                labels.append(int(label))
        return np.asarray(indices, dtype=np.int64), np.asarray(labels, dtype=np.int64)


def _validate_shapes(x, masks, window_games) -> None:
    if x.ndim != 3 or masks.shape != x.shape[:2] or len(window_games) != len(x):
        raise ValueError('Expected x[N,T,F], masks[N,T], window_games[N]')
    # Validate only masks, never read validation feature payloads during fitting.
    if masks.dtype != np.bool_:
        raise ValueError('Temporal masks must have boolean dtype')
    if np.any(masks.sum(axis=1) == 0) or np.any(np.diff(masks.astype(np.int8), axis=1) > 0):
        raise ValueError('Every window must have a nonempty, right-padded valid prefix')


def train_model(x, masks, window_games, games: pd.DataFrame, config: dict,
                checkpoint_dir: Path, device: str):
    """Fit fixed epochs (or predeclared time budget), never select on validation."""
    _validate_shapes(x, masks, window_games)
    seed = int(config.get('seed', 42))
    seed_everything(seed)
    device = torch.device(device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable; production must not silently use CPU')
    epochs = int(config.get('epochs', 5))
    budget = float(config.get('train_budget_seconds', 6300))
    if epochs < 1 or budget <= 0:
        raise ValueError('Epochs and training time budget must be positive')
    destination = checkpoint_destination(checkpoint_dir)
    sampler = IdentitySampler(window_games, games, config.get('batch_identities', 16),
                              config.get('windows_per_identity', 4), seed)
    model = make_model(config['variant'], x.shape[-1], tiny=bool(config.get('tiny', False))).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    history, step_seconds, diagnostics = [], [], []
    completed_epochs, steps, windows_seen = 0, 0, 0
    stopped_for_budget = False
    _sync(device)
    started = time.perf_counter()
    for epoch in range(epochs):
        epoch_start = time.perf_counter()
        losses = []
        model.train()
        for step_in_epoch in range(sampler.steps_per_epoch):
            elapsed = time.perf_counter() - started
            next_step_allowance = max(step_seconds[-20:], default=0.0) * 1.25
            if elapsed + next_step_allowance >= budget:
                stopped_for_budget = True
                break
            step_start = time.perf_counter()
            indices, labels = sampler.sample()
            batch_x = torch.as_tensor(np.asarray(x[indices], dtype=np.float32), device=device)
            batch_mask = torch.as_tensor(np.asarray(masks[indices]), device=device)
            batch_labels = torch.as_tensor(labels, device=device)
            if not bool(torch.isfinite(batch_x).all()):
                raise ValueError('Nonfinite input; physical normalization must impute missing channels')
            optimizer.zero_grad(set_to_none=True)
            embedding = model(batch_x, batch_mask)
            loss = supervised_contrastive_loss(embedding, batch_labels, temperature=0.1)
            if not bool(torch.isfinite(loss)):
                raise FloatingPointError('Nonfinite supervised contrastive loss')
            # Observe fixed steps only; never consume sampler/model RNG or select a model.
            observe = step_in_epoch in (0, sampler.steps_per_epoch - 1)
            if observe:
                snapshot = batch_diagnostics(embedding, batch_labels, batch_x, batch_mask)
                snapshot.update(epoch=epoch + 1, optimizer_step=steps + 1,
                                loss=float(loss.detach()),
                                learning_rates=[group['lr'] for group in optimizer.param_groups])
                output_before = model.output.weight.detach().clone()
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0,
                                                       error_if_nonfinite=True)
            if observe:
                snapshot['gradient_norm_pre_clip'] = float(grad_norm)
                input_weight = (model.input.weight if hasattr(model, 'input')
                                else model.encoder.weight_ih_l0)
                snapshot['input_weight_gradient_norm_after_clip'] = (
                    None if input_weight.grad is None else float(input_weight.grad.norm()))
            optimizer.step()
            if observe:
                snapshot['output_weight_step_delta_l2'] = float(
                    (model.output.weight.detach() - output_before).norm())
                diagnostics.append(snapshot)
                print(json.dumps({'training_diagnostic': snapshot}, allow_nan=False), flush=True)
            losses.append(float(loss.detach().cpu()))
            _sync(device)
            step_seconds.append(time.perf_counter() - step_start)
            steps += 1
            windows_seen += len(indices)
        if losses:
            history.append({'epoch': epoch + 1, 'steps': len(losses),
                            'loss': float(np.mean(losses)),
                            'seconds': time.perf_counter() - epoch_start,
                            'complete': len(losses) == sampler.steps_per_epoch})
            print(json.dumps({'training_epoch': history[-1]}), flush=True)
        if len(losses) == sampler.steps_per_epoch:
            completed_epochs += 1
        if stopped_for_budget:
            break
    _sync(device)
    fit_seconds = time.perf_counter() - started
    if steps == 0:
        raise RuntimeError('Time budget expired before any optimizer update')
    model.eval()
    checkpoint_path = destination / f"{config['variant'].lower()}_last.pt"
    # Last iterate only. No checkpoint selection or training-time validation.
    save_start = time.perf_counter()
    torch.save({'model': model.state_dict(), 'config': config, 'input_dim': int(x.shape[-1]),
                'completed_epochs': completed_epochs, 'optimizer_steps': steps,
                'test_opened': False, 'selection': 'last iterate; no early stopping'}, checkpoint_path)
    report = {
        'fit_split': 'train', 'train_seasons': list(TRAIN_SEASONS), 'test_opened': False,
        'seed': seed, 'device': str(device), 'torch_version': str(torch.__version__),
        'parameters': sum(p.numel() for p in model.parameters()),
        'requested_epochs': epochs, 'completed_epochs': completed_epochs,
        'optimizer_steps': steps, 'steps_per_epoch': sampler.steps_per_epoch,
        'train_windows': sampler.train_windows, 'sampled_windows': windows_seen,
        'train_identities': len(sampler.identities), 'single_game_identities': sampler.single_game_identities,
        'batch_identities': sampler.batch_identities, 'windows_per_identity': sampler.windows_per_identity,
        'train_budget_seconds': budget, 'stopped_for_budget': stopped_for_budget,
        'fit_seconds': fit_seconds, 'windows_per_second': windows_seen / fit_seconds,
        'mean_step_seconds': float(np.mean(step_seconds)),
        'projected_requested_fit_seconds': float(np.mean(step_seconds) * sampler.steps_per_epoch * epochs),
        'checkpoint': str(checkpoint_path), 'checkpoint_seconds': time.perf_counter() - save_start,
        'history': history, 'selection': 'last iterate; no early stopping',
        'diagnostics': diagnostics,
        'diagnostic_sampling': 'first and planned last step per epoch, if reached; train forward',
        'optimizer': {'name': 'AdamW', 'learning_rate': 3e-4, 'weight_decay': 1e-4,
                      'gradient_clip_norm': 1.0, 'temperature': 0.1},
    }
    return model, report


def benchmark(variant: str, input_dim: int, frames: int, batch_size: int = 64,
              steps: int = 8, threads: int = 1, device: str = 'cpu') -> dict:
    """Synthetic production-shape throughput; no empirical retrieval claims."""
    if batch_size < 4 or batch_size % 4 or steps < 1 or frames < 1 or input_dim < 1:
        raise ValueError('Benchmark needs positive sizes and batch size divisible by four')
    torch.set_num_threads(threads)
    seed_everything(42)
    target = torch.device(device)
    model = make_model(variant, input_dim).to(target)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    x = torch.randn(batch_size, frames, input_dim, device=target)
    mask = torch.ones(batch_size, frames, dtype=torch.bool, device=target)
    labels = torch.arange(batch_size, device=target) // 4
    train_times = []
    model.train()
    for step in range(steps + 2):
        _sync(target)
        start = time.perf_counter()
        opt.zero_grad(set_to_none=True)
        loss = supervised_contrastive_loss(model(x, mask), labels)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        _sync(target)
        if step >= 2:
            train_times.append(time.perf_counter() - start)
    infer_times = []
    model.eval()
    with torch.inference_mode():
        for step in range(steps + 2):
            _sync(target)
            start = time.perf_counter()
            model(x, mask)
            _sync(target)
            if step >= 2:
                infer_times.append(time.perf_counter() - start)
    return {'synthetic': True, 'variant': variant, 'device': str(target), 'threads': threads,
            'shape': [batch_size, frames, input_dim], 'measured_steps': steps, 'warmup_steps': 2,
            'parameters': sum(p.numel() for p in model.parameters()),
            'train_seconds_per_batch': float(np.mean(train_times)),
            'train_windows_per_second': batch_size / float(np.mean(train_times)),
            'inference_seconds_per_batch': float(np.mean(infer_times)),
            'inference_windows_per_second': batch_size / float(np.mean(infer_times)),
            'torch_version': str(torch.__version__)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true', required=True)
    parser.add_argument('--variant', choices=['v1', 'v2'], required=True)
    parser.add_argument('--input-dim', type=int, required=True)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--steps', type=int, default=8)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args(argv)
    print(json.dumps(benchmark(args.variant, args.input_dim, args.frames, args.batch_size,
                               args.steps, args.threads, args.device), indent=2))


if __name__ == '__main__':
    main()
