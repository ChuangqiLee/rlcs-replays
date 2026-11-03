"""Identity-supervised linear and MLP metrics on the handcrafted and channel-statistics summaries.

Post-freeze comparator for the fingerprint benchmark. The summaries that the unsupervised comparators rank by
standardized Euclidean distance (31 handcrafted features, the 76-dimensional matched channel statistics, the common
and the role-pooled channel statistics) are embedded by a train-only linear or MLP metric fit with the supervised
contrastive loss (``baselines.fit_summary``) and then scored with the unchanged retrieval protocol
(``evaluation.evaluate_methods``) against the handcrafted baseline. The benchmark population, gallery, queries and
bootstrap are unchanged; no encoder is trained. Final mode scores rlcs-2025 and requires AI_FINAL_OK=1.

Usage (inside a SLURM job, see slurm/ai_summary_metrics.sh):
  python -B -m ai_experiments.summary_metrics --cache artifacts/ai_cache/medium-w60-cap64 --scratch "$TMPDIR/x" \
      --out results/ai_dev/$SLURM_JOB_ID --checkpoints artifacts/ai_runs/$SLURM_JOB_ID --mode final --seeds 42,43,44
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
import torch

from .baselines import fit_summary
from .cache import load_cache
from .devrun import git_commit, relabel
from .evaluation import evaluate_methods

SOURCES = ('handcrafted', 'matched_handcrafted', 'common_summary', 'agent_summary')
KINDS = ('linear', 'mlp')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checkpoints', type=Path, required=True)
    parser.add_argument('--mode', choices=['dev', 'final'], default='dev')
    parser.add_argument('--dev-season', default='rlcs-2024')
    parser.add_argument('--seeds', default='42,43,44')
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--max-steps', type=int, default=10000)
    parser.add_argument('--budget-seconds', type=float, default=600.)
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args(argv)
    if '2026' in str(args.cache) or 'test' in Path(args.cache).resolve().parts:
        parser.error('2026/test caches are forbidden')
    if args.mode == 'final' and os.environ.get('AI_FINAL_OK') != '1':
        raise RuntimeError('final mode evaluates rlcs-2025; set AI_FINAL_OK=1 deliberately')
    device = torch.device(args.device)
    started = time.monotonic()
    data = load_cache(args.cache, args.scratch, need_agents=False, need_pooled=False)
    games, keep, metadata, train_seasons, eval_season = relabel(data.games, data.metadata, args.mode, args.dev_season)
    features = sorted(c for c in games if c.startswith('f_'))
    values = {'handcrafted': games[features].to_numpy(), 'matched_handcrafted': data.matched_handcrafted[keep],
              'common_summary': data.summaries[keep], 'agent_summary': data.agent_summaries[keep]}
    print(json.dumps(dict(cache=str(args.cache), games=int(len(games)), train_games=int((games.split == 'train').sum()),
                          dimensions={k: int(v.shape[1]) for k, v in values.items()}, eval_season=eval_season,
                          load_seconds=data.report['load_seconds'])), flush=True)
    eval_games = games.drop(columns=['season_original'])
    results = {}
    for seed in [int(s) for s in args.seeds.split(',')]:
        cfg = dict(seed=seed, epochs=args.epochs, max_steps=args.max_steps, train_budget_seconds=args.budget_seconds)
        methods = {name: dict(values=v, metric='euclidean', standardize=True) for name, v in values.items()}
        training = {}
        for source in SOURCES:
            for kind in KINDS:
                name = f'{source}_{kind}'
                z, record = fit_summary(values[source], games, cfg, args.checkpoints / f's{seed}' / name, device, kind)
                training[name] = {k: v for k, v in record.items() if k != 'transform'}
                methods[name] = dict(values=z, metric='cosine')
                print(json.dumps(dict(seed=seed, method=name, steps=record['optimizer_steps'], first_loss=record['first_loss'],
                                      final_loss=record['final_loss'], seconds=record['seconds'])), flush=True)
        evaluation = evaluate_methods(eval_games, metadata, methods, baseline='handcrafted', bootstrap=args.bootstrap, seed=42)
        evaluation['evaluation_season_original'] = eval_season
        evaluation['mode'] = args.mode
        out = args.out / f'summary_metrics_s{seed}'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'evaluation.json').write_text(json.dumps(evaluation, indent=1, default=float))
        summary = ({m: {k: evaluation['primary']['methods'][m]['metrics'][k]['estimate'] for k in ('top1', 'top5', 'mrr')}
                    for m in evaluation['primary'].get('methods', {})} if evaluation.get('status') == 'fit' else evaluation)
        report = dict(preset=f'summary_metrics_s{seed}', config=cfg, mode=args.mode, seed=seed, train_seasons=list(train_seasons),
                      eval_season=eval_season, sources=list(SOURCES), kinds=list(KINDS), training=training, summary=summary,
                      git_commit=git_commit(), device=str(device), test_opened=False, seconds=time.monotonic() - started)
        (out / 'training.json').write_text(json.dumps(report, indent=1, default=float))
        results[seed] = summary
        print(json.dumps(dict(seed=seed, summary=summary), indent=1), flush=True)
    (args.out / 'summary.json').write_text(json.dumps(dict(mode=args.mode, results=results, seconds=time.monotonic() - started),
                                                     indent=1, default=float))


if __name__ == '__main__':
    main()
