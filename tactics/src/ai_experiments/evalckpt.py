"""Evaluate saved fingerprint checkpoints on the shared retrieval benchmark.

Usage: python -m ai_experiments.evalckpt --cache <dir> --scratch <dir> --out <dir>
           --checkpoint <path> [--checkpoint <path> ...] --mode dev|final [--bootstrap N]
Checkpoints trained in dev mode may only be evaluated in dev mode; final mode
requires AI_FINAL_OK=1 and checkpoints trained on all training seasons.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
import torch

from .cache import load_cache
from .devrun import embed_all, relabel
from .evaluation import evaluate_methods
from .fingerprint import FingerprintModel, Standardizer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, action='append', required=True)
    parser.add_argument('--mode', choices=['dev', 'final'], default='dev')
    parser.add_argument('--dev-season', default='rlcs-2024')
    parser.add_argument('--bootstrap', type=int, default=200)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args(argv)
    if args.mode == 'final' and os.environ.get('AI_FINAL_OK') != '1':
        raise RuntimeError('final mode evaluates rlcs-2025; set AI_FINAL_OK=1 deliberately')
    device = torch.device(args.device)
    data = load_cache(args.cache, args.scratch, need_pooled=False)
    games, keep, metadata, train_seasons, eval_season = relabel(data.games, data.metadata, args.mode, args.dev_season)
    original_index = np.flatnonzero(keep)
    new_index = -np.ones(len(data.games), dtype=np.int64)
    new_index[original_index] = np.arange(len(original_index))
    windows_by_game = [[] for _ in range(len(games))]
    for row, game in enumerate(data.window_games):
        g = new_index[game]
        if g >= 0:
            windows_by_game[g].append(row)
    windows_by_game = [np.asarray(w, dtype=np.int64) for w in windows_by_game]
    features = sorted(c for c in games if c.startswith('f_'))
    eval_games = games.drop(columns=['season_original'])
    methods = {'handcrafted': dict(values=games[features].to_numpy(), metric='euclidean', standardize=True),
               'common_summary': dict(values=data.summaries[keep], metric='euclidean', standardize=True),
               'agent_summary': dict(values=data.agent_summaries[keep], metric='euclidean', standardize=True)}
    embeddings = {}
    for path in args.checkpoint:
        ckpt = torch.load(path, map_location='cpu', weights_only=False)
        if ckpt['mode'] != args.mode or list(ckpt['train_seasons']) != list(train_seasons):
            raise RuntimeError(f'{path}: trained for mode {ckpt["mode"]} on {ckpt["train_seasons"]}')
        cfg = ckpt['config']
        state = ckpt['state_dict']
        std = Standardizer(state['encoder.standardizer.mean'], state['encoder.standardizer.std'])
        model = FingerprintModel(cfg, ckpt['n_classes'], std).to(device)
        missing, unexpected = model.load_state_dict(state, strict=False)
        shared = model.encoder.projected_games is False
        if unexpected or [k for k in missing if not (shared and k == 'game_classifier.weight')]:
            raise RuntimeError(f'{path}: state mismatch missing={missing} unexpected={unexpected}')
        name = path.stem
        started = time.monotonic()
        g = embed_all(model, data.x, data.masks, windows_by_game, len(games), device, int(cfg['max_eval_windows']))
        print(json.dumps(dict(checkpoint=str(path), embed_seconds=time.monotonic() - started)), flush=True)
        embeddings[name] = g
        methods[f'learned:{name}'] = dict(values=g, metric='cosine')
        methods[f'centered:{name}'] = dict(values=g, metric='cosine', center=True)
        methods[f'fusion:{name}'] = dict(components=['handcrafted', f'learned:{name}'], weights=[.5, .5])
    evaluation = evaluate_methods(eval_games, metadata, methods, baseline='handcrafted', bootstrap=args.bootstrap, seed=42)
    evaluation['evaluation_season_original'] = eval_season
    evaluation['mode'] = args.mode
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'evaluation.json').write_text(json.dumps(evaluation, indent=1, default=float))
    np.savez_compressed(args.out / 'embeddings.npz', **embeddings)
    summary = {m: {k: round(evaluation['primary']['methods'][m]['metrics'][k]['estimate'], 4) for k in ('top1', 'top5', 'mrr')}
               for m in evaluation['primary']['methods']}
    paired = {m: evaluation['primary']['methods'][m]['paired_difference_vs_baseline']['top1'] for m in evaluation['primary']['methods']}
    print(json.dumps(dict(summary=summary, paired_top1=paired), indent=1, default=float), flush=True)


if __name__ == '__main__':
    main()
