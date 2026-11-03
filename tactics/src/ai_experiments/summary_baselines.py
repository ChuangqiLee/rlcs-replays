"""Game-level summary baselines on the development split (no windows needed).

Measures how much identity information the model's own input channels carry
when reduced to per-game mean/SD statistics: nearest-class-mean retrieval via
the shared evaluator, plus a multinomial logistic probe over training
identities scored by top-1 on the development season's player-series queries.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .devrun import relabel
from .evaluation import evaluate_methods, train_standardize


def logistic_probe(values, games, seed=42, max_iter=300):
    from sklearn.linear_model import LogisticRegression
    train = games.split.to_numpy() == 'train'
    x, _ = train_standardize(values, train)
    ids = sorted(games.identity_id[train].unique())
    label = {i: k for k, i in enumerate(ids)}
    y = games.identity_id.map(label)
    clf = LogisticRegression(max_iter=max_iter, C=1., n_jobs=2)
    clf.fit(x[train], y[train].astype(int))
    val = ~train & games.identity_id.isin(ids).to_numpy()
    proba = clf.predict_proba(x[val])
    # Player-series queries: average log-probabilities over the series' games.
    frame = pd.DataFrame(dict(identity=games.identity_id[val].to_numpy(), series=games.series_id[val].to_numpy()))
    frame['logp'] = list(np.log(np.clip(proba, 1e-9, 1.)))
    hits, n = 0, 0
    for (identity, _), g in frame.groupby(['identity', 'series']):
        mean = np.mean(np.stack(g.logp.to_list()), 0)
        hits += int(clf.classes_[mean.argmax()] == label[identity])
        n += 1
    return dict(train_games=int(train.sum()), classes=len(ids), train_accuracy=float(clf.score(x[train], y[train].astype(int))),
                series_queries=n, series_top1=hits / max(n, 1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--dev-season', default='rlcs-2024')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bootstrap', type=int, default=200)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args(argv)
    games = pd.read_parquet(args.cache / 'games.parquet')
    metadata = json.loads((args.cache / 'metadata.json').read_text())
    with np.load(args.cache / 'summaries.npz') as z:
        summaries, agent = z['summaries'], z['agent_summaries']
    games, keep, metadata, train_seasons, eval_season = relabel(games, metadata, 'dev', args.dev_season)
    features = sorted(c for c in games if c.startswith('f_'))
    methods = {'handcrafted': dict(values=games[features].to_numpy(), metric='euclidean', standardize=True),
               'common_summary': dict(values=summaries[keep], metric='euclidean', standardize=True),
               'agent_summary': dict(values=agent[keep], metric='euclidean', standardize=True),
               'fusion_hand_agent': dict(components=['handcrafted', 'agent_summary'], weights=[.5, .5])}
    started = time.perf_counter()
    report = evaluate_methods(games.drop(columns=['season_original']), metadata, methods, baseline='handcrafted',
                              bootstrap=args.bootstrap, seed=42)
    summary = {m: {k: round(report['primary']['methods'][m]['metrics'][k]['estimate'], 4) for k in ('top1', 'top5', 'mrr')}
               for m in report['primary']['methods']}
    paired = {m: report['primary']['methods'][m]['paired_difference_vs_baseline']['top1'] for m in report['primary']['methods']}
    out = dict(dev_season=eval_season, train_seasons=list(train_seasons), summary=summary, paired_top1_vs_handcrafted=paired,
               population={k: report['population'][k] for k in ('n_gallery', 'eligible_before_region')},
               queries=report['primary']['queries_evaluated'], seconds=time.perf_counter() - started)
    if args.probe:
        out['logistic_probe'] = {name: logistic_probe(values, games) for name, values in
                                 (('handcrafted', games[features].to_numpy()), ('agent_summary', agent[keep]))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(out, full=report), indent=1, default=float))
    print(json.dumps({k: v for k, v in out.items()}, indent=1, default=float))


if __name__ == '__main__':
    main()
