"""Train/evaluate fingerprint encoders from the window cache.

Modes:
  dev   -- fit on the training seasons except ``--dev-season`` (default rlcs-2024),
           evaluate retrieval on that season; the 2025 season is dropped entirely.
           All model selection happens here.
  final -- fit on all training seasons, evaluate once on rlcs-2025 with the
           shared paired-bootstrap benchmark (``evaluation.evaluate_methods``).
Several presets can run sequentially in one job. Outputs under ``--out``:
<preset>/training.json, evaluation.json, embeddings.npz; checkpoints under
``--checkpoints``.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import TRAIN_SEASONS, VAL_SEASON
from .cache import load_cache
from .diagnostics import embedding_diagnostics
from .evaluation import evaluate_methods
from .fingerprint import FingerprintModel, Standardizer

BASE = dict(width=128, heads=4, spatial_layers=2, temporal_layers=2, temporal='transformer',
            inputs='agents', context_token=True, dropout=.1, ghost_prob=.15, standardize=True,
            embedding=128, scale=30., margin=0., w_window_ce=1., w_game_ce=1., w_supcon=0.,
            temperature=.1, batch_identities=32, windows_per_game=8, steps=10000, lr=1e-3,
            weight_decay=.05, warmup=1000, clip=1., seed=42, amp=True, eval_every=0,
            max_eval_windows=64, bootstrap=200, log_every=50, mirror_prob=0.,
            role_init=.02, pos_scale=.1, bnneck=True, probe_steps=200, game_pool='mean', raw_skip=False)

PRESETS = {
    'ce_both': {},
    'v1recipe': dict(scale=16., lr=5e-4, warmup=300, steps=6000, role_init=1., pos_scale=1., bnneck=False),
    'nobn': dict(bnneck=False),
    'bigrole': dict(role_init=1.),
    'pos1': dict(pos_scale=1.),
    'lr5e-4': dict(lr=5e-4),
    's16': dict(scale=16.),
    's64': dict(scale=64.),
    'steps6k': dict(steps=6000),
    'steps20k': dict(steps=20000),
    'ce_window': dict(w_game_ce=0.),
    'ce_game': dict(w_window_ce=0.),
    'ce_both_supcon': dict(w_supcon=1.),
    'supcon_only': dict(w_window_ce=0., w_game_ce=0., w_supcon=1.),
    'ce_both_margin': dict(margin=.2),
    'gru': dict(temporal='gru'),
    'mamba': dict(temporal='mamba'),
    'pooled38': dict(inputs='pooled'),
    'nostd': dict(standardize=False),
    'noghost': dict(ghost_prob=0.),
    'nocontext': dict(context_token=False),
    'k16': dict(windows_per_game=16),
    'k32': dict(windows_per_game=32),
    'k48': dict(windows_per_game=48),
    'k4': dict(windows_per_game=4),
    'b64': dict(batch_identities=64),
    'width256': dict(width=256, heads=8),
    'deep': dict(spatial_layers=3, temporal_layers=4),
    'mirror': dict(mirror_prob=.5),
    'long': dict(steps=20000),
    'meanstd': dict(game_pool='meanstd'),
    'skip': dict(raw_skip=True),
    'skipms': dict(game_pool='meanstd', raw_skip=True),
}


def git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parents[2]).stdout.strip()
    except OSError:
        return None


def relabel(games, metadata, mode, dev_season):
    """Return (games, metadata, train_seasons, eval_season) for the mode."""
    games = games.reset_index(drop=True)
    games['season_original'] = games.season
    if mode == 'dev':
        if dev_season not in TRAIN_SEASONS:
            raise ValueError('dev season must be a training season')
        # The frozen evaluator requires split to follow the season name, so the
        # development season is presented under the evaluation-season name. No
        # rlcs-2025 row survives this filter; its windows are never read.
        keep = games.season != VAL_SEASON
        games = games[keep].reset_index(drop=True)
        is_dev = games.season == dev_season
        games['split'] = np.where(is_dev, 'val', 'train')
        games['season'] = np.where(is_dev, VAL_SEASON, games.season)
        metadata = [dict(m, split='val' if m['season'] == dev_season else 'train',
                         season=VAL_SEASON if m['season'] == dev_season else m['season'],
                         season_original=m['season'])
                    for m in metadata if m['season'] != VAL_SEASON]
        train_seasons = tuple(s for s in TRAIN_SEASONS if s != dev_season)
        return games, keep.to_numpy(), metadata, train_seasons, dev_season
    if mode == 'final':
        return games, np.ones(len(games), dtype=bool), list(metadata), TRAIN_SEASONS, VAL_SEASON
    raise ValueError('mode must be dev or final')


class Sampler:
    """Identities uniformly; two distinct games (different series preferred); K windows each."""
    def __init__(self, games, windows_by_game, cfg, rng):
        train = games[games.split == 'train']
        self.rng = rng
        self.k = int(cfg['windows_per_game'])
        self.batch_identities = int(cfg['batch_identities'])
        self.identities = sorted(train.identity_id.unique())
        self.label_of = {identity: i for i, identity in enumerate(self.identities)}
        self.games_of = {identity: group.index.to_numpy()
                         for identity, group in train.groupby('identity_id', sort=True)}
        self.pairable = [i for i in self.identities if len(self.games_of[i]) >= 2]
        if len(self.pairable) < 2:
            raise ValueError('Need two identities with two training games')
        self.series = games.series_id.astype(str).to_numpy()
        self.windows_by_game = windows_by_game
        self.n_classes = len(self.identities)
        self.train_windows = int(sum(len(windows_by_game[g]) for g in train.index))

    def sample(self):
        chosen = self.rng.choice(len(self.pairable), min(self.batch_identities, len(self.pairable)), replace=False)
        game_rows, labels, window_rows, bag = [], [], [], []
        for c in chosen:
            identity = self.pairable[c]
            available = self.games_of[identity]
            first = int(self.rng.choice(available))
            others = available[available != first]
            different = others[self.series[others] != self.series[first]]
            second = int(self.rng.choice(different if len(different) else others))
            for game in (first, second):
                w = self.windows_by_game[game]
                pick = self.rng.choice(w, self.k, replace=len(w) < self.k)
                bag.extend([len(game_rows)] * len(pick))
                window_rows.extend(pick.tolist())
                game_rows.append(game)
                labels.append(self.label_of[identity])
        return (np.asarray(window_rows), np.asarray(bag), np.asarray(labels),
                np.asarray(game_rows))


def fit_standardizer(x, masks, train_window_rows, rng, n=20000):
    rows = np.sort(rng.choice(train_window_rows, min(n, len(train_window_rows)), replace=False))
    values = torch.as_tensor(x[rows].astype(np.float32))
    m = torch.as_tensor(masks[rows])
    valid = values[m]
    mean, std = valid.mean(0), valid.std(0)
    std = torch.where(std < 1e-3, torch.ones_like(std), std)
    mean = torch.where(std == 1., torch.zeros_like(mean), mean)
    return mean, std


def mirror(x):
    """Reflect the field across the x = 0 plane: negate x and vx for every agent."""
    x = x.clone()
    x[..., 0] *= -1
    x[..., 3] *= -1
    return x


def embed_all(model, x, masks, windows_by_game, n_games, device, cap, batch_windows=1024):
    """Game embeddings for every game from up to ``cap`` windows each."""
    model.eval()
    rows, bag = [], []
    for g in range(n_games):
        w = windows_by_game[g][:cap]
        rows.extend(w.tolist())
        bag.extend([g] * len(w))
    rows, bag = np.asarray(rows), np.asarray(bag)
    order = np.argsort(rows)
    rows, bag = rows[order], bag[order]
    enc = model.encoder
    acc = None
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16, enabled=device.type == 'cuda'):
        for start in range(0, len(rows), batch_windows):
            r = rows[start:start + batch_windows]
            xb = torch.as_tensor(x[r].astype(np.float32), device=device)
            mb = torch.as_tensor(masks[r], device=device)
            z, stats = enc.window_embeddings(xb, mb, return_stats=True)
            z = z.float()
            stats = tuple(s.float() for s in stats) if stats is not None else None
            part = enc.game_sums(z, torch.as_tensor(bag[start:start + batch_windows], device=device), n_games, stats)
            acc = list(part) if acc is None else [None if a is None else a + b for a, b in zip(acc, part)]
        counts = acc[2].cpu().numpy()
        if np.any(counts == 0):
            raise AssertionError('Every game must have a window')
        out = torch.cat([enc.finalize(*[None if a is None else a[s:s + 4096] for a in acc])
                         for s in range(0, n_games, 4096)]).float()
    return out.cpu().numpy()


def memorization_probe(cfg, n_classes, standardizer, sampler, x, masks, device, steps=200, lr=3e-3):
    """Fresh model, one fixed batch: can the architecture memorize at all?"""
    torch.manual_seed(int(cfg['seed']) + 7)
    model = FingerprintModel(cfg, n_classes, standardizer).to(device)
    rows, bag, labels, game_rows = sampler.sample()
    order = np.argsort(rows)
    xb = torch.as_tensor(x[rows[order]].astype(np.float32), device=device)
    mb = torch.as_tensor(masks[rows[order]], device=device)
    bag_t = torch.as_tensor(bag[order], device=device)
    game_labels = torch.as_tensor(labels, device=device)
    window_labels = game_labels[bag_t]
    model.eval()
    with torch.no_grad():
        z0 = model.encoder.window_embeddings(xb, mb).float()
        cos = z0 @ z0.T
        init = dict(window_cosine_mean=float(cos[~torch.eye(len(z0), dtype=torch.bool, device=device)].mean()),
                    window_feature_variance=float(z0.var(0).mean()))
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.)
    history = []
    for step in range(steps):
        optimizer.zero_grad(set_to_none=True)
        loss, terms, _ = model(xb, mb, bag_t, len(game_rows), window_labels, game_labels)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        if step % 20 == 0 or step == steps - 1:
            history.append(dict(step=step, loss=float(loss), **terms))
    return dict(initial=init, history=history, games=len(game_rows), windows=int(len(rows)), lr=lr, steps=steps,
                memorized=bool(history[-1].get('game_acc', 0.) >= .9))


def run_preset(name, cfg, data, mode, dev_season, out, ckpt_dir, device):
    out.mkdir(parents=True, exist_ok=True)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(int(cfg['seed']))
    rng = np.random.default_rng(int(cfg['seed']))
    games, keep, metadata, train_seasons, eval_season = relabel(data.games, data.metadata, mode, dev_season)
    # Map original game indices -> relabeled indices; windows of dropped games are never used.
    original_index = np.flatnonzero(keep)
    new_index = -np.ones(len(data.games), dtype=np.int64)
    new_index[original_index] = np.arange(len(original_index))
    windows_by_game = [[] for _ in range(len(games))]
    for row, game in enumerate(data.window_games):
        g = new_index[game]
        if g >= 0:
            windows_by_game[g].append(row)
    windows_by_game = [np.asarray(w, dtype=np.int64) for w in windows_by_game]
    assert set(games[games.split == 'train'].season_original) <= set(train_seasons)
    assert set(games[games.split == 'val'].season_original) == {eval_season}
    assert VAL_SEASON not in set(games.season_original) or mode == 'final'
    sampler = Sampler(games, windows_by_game, cfg, rng)
    train_rows = np.concatenate([windows_by_game[g] for g in games.index[games.split == 'train']])
    x = data.x if cfg['inputs'] == 'agents' else data.x  # pooled channels are derived in-model
    mean, std = fit_standardizer(x, data.masks, train_rows, rng)
    if cfg['inputs'] == 'pooled':
        from .models import pooled_channels
        rows = np.sort(rng.choice(train_rows, min(20000, len(train_rows)), replace=False))
        pv = pooled_channels(torch.as_tensor(x[rows].astype(np.float32)))
        valid = pv[torch.as_tensor(data.masks[rows])]
        mean, std = valid.mean(0), valid.std(0)
        std = torch.where(std < 1e-3, torch.ones_like(std), std)
        mean = torch.where(std == 1., torch.zeros_like(mean), mean)
    probe = None
    if int(cfg.get('probe_steps', 0)) > 0:
        probe = memorization_probe(cfg, sampler.n_classes, Standardizer(mean, std), sampler, x, data.masks,
                                   device, int(cfg['probe_steps']))
        print(json.dumps(dict(preset=name, probe=dict(initial=probe['initial'], final=probe['history'][-1],
                                                      memorized=probe['memorized']))), flush=True)
    model = FingerprintModel(cfg, sampler.n_classes, Standardizer(mean, std)).to(device)
    decay, no_decay = [], []
    for n_, p in model.named_parameters():
        (no_decay if p.ndim < 2 or 'norm' in n_ or 'ghost' in n_ else decay).append(p)
    optimizer = torch.optim.AdamW([dict(params=decay, weight_decay=float(cfg['weight_decay'])),
                                   dict(params=no_decay, weight_decay=0.)], lr=float(cfg['lr']), betas=(.9, .98))
    steps, warmup = int(cfg['steps']), int(cfg['warmup'])
    def lr_at(step):
        if step < warmup:
            return (step + 1) / warmup
        progress = (step - warmup) / max(1, steps - warmup)
        return .05 + .95 * .5 * (1 + math.cos(math.pi * progress))
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_at)
    history, started = [], time.monotonic()
    model.train()
    amp = bool(cfg['amp']) and device.type == 'cuda'
    for step in range(steps):
        rows, bag, labels, game_rows = sampler.sample()
        order = np.argsort(rows)
        xb = torch.as_tensor(x[rows[order]].astype(np.float32), device=device)
        mb = torch.as_tensor(data.masks[rows[order]], device=device)
        bag_t = torch.as_tensor(bag[order], device=device)
        game_labels = torch.as_tensor(labels, device=device)
        window_labels = game_labels[bag_t]
        if cfg['mirror_prob'] > 0 and rng.random() < cfg['mirror_prob']:
            xb = mirror(xb)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda', dtype=torch.bfloat16, enabled=amp):
            loss, terms, _ = model(xb, mb, bag_t, len(game_rows), window_labels, game_labels)
        if not torch.isfinite(loss):
            raise FloatingPointError(f'Nonfinite loss at step {step}')
        loss.backward()
        grad = torch.nn.utils.clip_grad_norm_(model.parameters(), float(cfg['clip']))
        optimizer.step()
        scheduler.step()
        if step % int(cfg['log_every']) == 0 or step == steps - 1:
            record = dict(step=step, loss=float(loss), grad=float(grad), lr=scheduler.get_last_lr()[0],
                          seconds=time.monotonic() - started, **terms)
            history.append(record)
            print(json.dumps(dict(preset=name, **record)), flush=True)
    fit_seconds = time.monotonic() - started
    torch.save(dict(state_dict=model.state_dict(), config=cfg, n_classes=sampler.n_classes,
                    identities=sampler.identities, mode=mode, eval_season=eval_season,
                    train_seasons=list(train_seasons)), ckpt_dir / f'{name}.pt')
    embed_start = time.monotonic()
    g = embed_all(model, x, data.masks, windows_by_game, len(games), device, int(cfg['max_eval_windows']))
    embed_seconds = time.monotonic() - embed_start
    features = sorted(c for c in games if c.startswith('f_'))
    eval_games = games.drop(columns=['season_original'])
    methods = {'handcrafted': dict(values=games[features].to_numpy(), metric='euclidean', standardize=True),
               'learned': dict(values=g, metric='cosine'),
               'learned_centered': dict(values=g, metric='cosine', center=True),
               'fusion': dict(components=['handcrafted', 'learned'], weights=[.5, .5])}
    methods['common_summary'] = dict(values=data.summaries[keep], metric='euclidean', standardize=True)
    methods['agent_summary'] = dict(values=data.agent_summaries[keep], metric='euclidean', standardize=True)
    if mode == 'final':
        methods['matched_handcrafted'] = dict(values=data.matched_handcrafted[keep], metric='euclidean', standardize=True)
    evaluation = evaluate_methods(eval_games, metadata, methods, baseline='handcrafted',
                                  bootstrap=int(cfg['bootstrap']), seed=42)
    evaluation['evaluation_season_original'] = eval_season
    evaluation['mode'] = mode
    train_labels = games.identity_id.to_numpy()[games.split.to_numpy() == 'train']
    diag = embedding_diagnostics(g[games.split.to_numpy() == 'train'][:5000], train_labels[:5000])
    summary = {m: {k: evaluation['primary']['methods'][m]['metrics'][k]['estimate'] for k in ('top1', 'top5', 'mrr')}
               for m in evaluation['primary'].get('methods', {})} if evaluation.get('status') == 'fit' else evaluation
    report = dict(preset=name, config=cfg, mode=mode, train_seasons=list(train_seasons), eval_season=eval_season,
                  n_classes=sampler.n_classes, pairable_identities=len(sampler.pairable),
                  train_windows=sampler.train_windows, parameters=sum(p.numel() for p in model.parameters()),
                  encoder_parameters=sum(p.numel() for p in model.encoder.parameters()),
                  fit_seconds=fit_seconds, embed_seconds=embed_seconds, history=history, probe=probe,
                  train_embedding_diagnostics=diag, summary=summary, git_commit=git_commit(),
                  device=str(device), test_opened=False)
    (out / 'training.json').write_text(json.dumps(report, indent=1, default=float))
    (out / 'evaluation.json').write_text(json.dumps(evaluation, indent=1, default=float))
    np.savez_compressed(out / 'embeddings.npz', learned=g, game_keys=games[['identity_id', 'season', 'replay_id']].to_numpy().astype(str))
    print(json.dumps(dict(preset=name, summary=summary, fit_seconds=fit_seconds, embed_seconds=embed_seconds)), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checkpoints', type=Path, required=True)
    parser.add_argument('--mode', choices=['dev', 'final'], default='dev')
    parser.add_argument('--dev-season', default='rlcs-2024')
    parser.add_argument('--presets', default='ce_both')
    parser.add_argument('--override', action='append', default=[], help='key=json applied to every preset')
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args(argv)
    if '2026' in str(args.cache) or 'test' in Path(args.cache).resolve().parts:
        parser.error('2026/test caches are forbidden')
    device = torch.device(args.device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    overrides = {}
    for item in args.override:
        key, value = item.split('=', 1)
        overrides[key] = json.loads(value)
    started = time.monotonic()
    data = load_cache(args.cache, args.scratch, need_pooled=False)
    print(json.dumps(dict(cache=str(args.cache), windows=int(len(data.masks)), games=int(len(data.games)),
                          load_seconds=data.report['load_seconds'])), flush=True)
    if args.mode == 'final' and os.environ.get('AI_FINAL_OK') != '1':
        raise RuntimeError('final mode evaluates rlcs-2025; set AI_FINAL_OK=1 deliberately')
    results = {}
    for name in args.presets.split(','):
        cfg = deepcopy(BASE)
        for part in name.split('+'):
            cfg.update(PRESETS[part])
        cfg.update(overrides)
        results[name] = run_preset(name, cfg, data, args.mode, args.dev_season, args.out / name,
                                   args.checkpoints, device)['summary']
    (args.out / 'summary.json').write_text(json.dumps(dict(mode=args.mode, dev_season=args.dev_season,
                                                          results=results, seconds=time.monotonic() - started), indent=1))
    print(json.dumps(results, indent=1), flush=True)


if __name__ == '__main__':
    main()
