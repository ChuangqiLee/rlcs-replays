"""Isolated V3/V4 train-only fitting, retaining the original budget and loss."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import TRAIN_SEASONS

from .models import supervised_contrastive_loss
from .training import IdentitySampler, seed_everything, checkpoint_destination, _sync


def make_model(variant: str, input_dim: int, tiny: bool = False):
    if variant == 'v3':
        from .models_v3 import UniTrajEncoder
        model = UniTrajEncoder(input_dim=input_dim, tiny=tiny)
        expected = 1121408
    elif variant == 'v4':
        from .models_v4 import TiRexEncoder
        model = TiRexEncoder(input_dim=input_dim, tiny=tiny)
        expected = 708992
    else:
        raise ValueError('Adapted training accepts only v3/v4')
    if not tiny and sum(p.numel() for p in model.parameters()) != expected:
        raise AssertionError('Model parameter count differs from preregistration')
    return model


def _validate_shapes(x, masks, window_games) -> None:
    if x.ndim not in (3, 4) or masks.shape != x.shape[:2] or len(window_games) != len(x):
        raise ValueError('Expected x[N,T,F] or x[N,T,A,F], masks[N,T], window_games[N]')
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
    if config['variant'] == 'v4':
        from .sampling_v4 import ContextIdentitySampler
        sampler_class = ContextIdentitySampler
    else:
        sampler_class = IdentitySampler
    sampler = sampler_class(window_games, games, config.get('batch_identities', 16),
                              config.get('windows_per_identity', 4), seed)
    model = make_model(config['variant'], x.shape[-1], tiny=bool(config.get('tiny', False))).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    history, step_seconds = [], []
    completed_epochs, steps, windows_seen = 0, 0, 0
    stopped_for_budget = False
    _sync(device)
    started = time.perf_counter()
    for epoch in range(epochs):
        epoch_start = time.perf_counter()
        losses = []
        model.train()
        for _ in range(sampler.steps_per_epoch):
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
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
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
        'optimizer': {'name': 'AdamW', 'learning_rate': 3e-4, 'weight_decay': 1e-4,
                      'gradient_clip_norm': 1.0, 'temperature': 0.1},
    }
    report['base_batch_size'] = sampler.batch_size
    if config['variant'] == 'v4':
        report['context_negatives'] = sampler.report()
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
    shape = (batch_size, frames, 7, input_dim) if variant == 'v3' else (batch_size, frames, input_dim)
    x = torch.randn(shape, device=target)
    if variant == 'v3':
        x[..., -1] = 1.  # All synthetic agents available; real builder supplies indicators.
    mask = torch.ones(batch_size, frames, dtype=torch.bool, device=target)
    labels = torch.arange(batch_size, device=target) // 4
    if variant == 'v4' and batch_size == 96:
        # Maximum preregistered batch: 16 base identities x4 and 16 extras x2.
        labels = torch.cat((torch.arange(16, device=target).repeat_interleave(4),
                            torch.arange(16, 32, device=target).repeat_interleave(2)))
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
    # The shared embed_games evaluator always uses batches of 64, including V4.
    inference_x, inference_mask = x[:64], mask[:64]
    model.eval()
    with torch.inference_mode():
        for step in range(steps + 2):
            _sync(target)
            start = time.perf_counter()
            model(inference_x, inference_mask)
            _sync(target)
            if step >= 2:
                infer_times.append(time.perf_counter() - start)
    return {'synthetic': True, 'variant': variant, 'device': str(target), 'threads': threads,
            'shape': list(shape), 'inference_shape': list(inference_x.shape),
            'measured_steps': steps, 'warmup_steps': 2,
            'parameters': sum(p.numel() for p in model.parameters()),
            'train_seconds_per_batch': float(np.mean(train_times)),
            'train_windows_per_second': batch_size / float(np.mean(train_times)),
            'inference_seconds_per_batch': float(np.mean(infer_times)),
            'inference_windows_per_second': len(inference_x) / float(np.mean(infer_times)),
            'torch_version': str(torch.__version__)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true', required=True)
    parser.add_argument('--variant', choices=['v3', 'v4'], required=True)
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
