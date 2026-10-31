"""Development-only RQ4 habit stability; frozen methods in docs/RQ4_habits_prereg.md.

Run in an integrated checkout: python -m tactics_code.habit_stability --compact PATH
The local overlay also supports direct script execution with the reference src on
PYTHONPATH. Never discovers or opens held-out compact directories.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
import warnings

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from statsmodels.formula.api import mixedlm

from tactics_code.data import parsed_json, roster_key
from tactics_code.screen import (ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON,
                                 guard_path, metadata_inventory, read_slice, REQUIRED)
from tactics_code.style_retrieval import check_rows

HABITS = ('last_man_share', 'own_goal_depth', 'own_third_depth', 'boost_mean',
          'supersonic_share', 'ball_proximity_share', 'aerial_share', 'rotation_back_speed')
MIN_SECONDS, MIN_REPLAYS, MIN_PLAYERS = 10., 10, 20
BOOTSTRAP, PERMUTATIONS, SEED = 2000, 2000, 42
MIN_CELLS, MIN_MODEL_PLAYERS, MIN_ROSTERS, MIN_SWITCHERS = 30, 10, 5, 3
REQUIRED_VALID_FRACTION = .95
KEYS = ['identity_id', 'season', 'roster_id']
DEFAULT_COMPACT = Path('artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact')


def metadata_ids(meta):
    check_rows(pd.DataFrame([meta]))
    ids = parsed_json(meta.get('player_ids'), [])
    if (len(ids) != 6 or any(not isinstance(x, str) or not x for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Six distinct stable player IDs required')
    if meta.get('roster_id') != roster_key(ids[:3]):
        raise ValueError('roster_id must match exact own-team player membership')
    return ids


def roster_history(metadata):
    """All metadata, including replays whose habit exposure is insufficient."""
    history = defaultdict(dict)
    seen = set()
    for meta in metadata:
        ids = metadata_ids(meta)
        for identity in ids[:3]:
            key = (identity, meta['replay_id'])
            if key in seen:
                raise ValueError('Duplicate player-replay metadata')
            seen.add(key)
            history[(identity, meta['season'])][meta['roster_id']] = frozenset(ids[:3]) - {identity}
    return history


def validate_pairs(pairs):
    for pair in pairs:
        if len(pair) != 2 or {int(m['focal_team']) for m in pair} != {0, 1}:
            raise ValueError('Exactly two opposing perspectives required')
        a, b = [metadata_ids(m) for m in pair]
        if set(a[:3]) != set(b[3:]) or set(a[3:]) != set(b[:3]):
            raise ValueError('Inconsistent perspective player IDs')
        if len({(m['replay_id'], m['series_id'], m['season'], m['split']) for m in pair}) != 1:
            raise ValueError('Inconsistent replay grouping')
    return roster_history([m for pair in pairs for m in pair])


def validate_offsets(pairs, schema):
    """Validate every replay's layout and bounds before opening any payload."""
    for pair in pairs:
        for meta in pair:
            start, stop = int(meta['start']), int(meta['stop'])
            if start != meta['start'] or stop != meta['stop']:
                raise ValueError('Noninteger replay slice bounds')
            for key in REQUIRED:
                header = schema[meta['_shard']][key]
                if (header['fortran'] or np.dtype(header['dtype']).hasobject
                        or not header['shape'] or not 0 <= start < stop <= header['shape'][0]):
                    raise ValueError('Invalid compact array layout or replay slice bounds')


def game_habits(meta, arrays):
    """Read-only arrays supported; all masks and derived quantities are new arrays."""
    ids = metadata_ids(meta)
    fps = float(meta['fps'])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError('Positive finite sample frequency required')
    t = np.asarray(arrays['time'])
    p, ball = np.asarray(arrays['players']), np.asarray(arrays['ball'])
    if p.shape != (len(t), 6, 8) or ball.shape != (len(t), 6):
        raise ValueError('Unexpected compact player/ball layout')
    if any(np.asarray(arrays[k]).shape != t.shape for k in ('live', 'segment')):
        raise ValueError('Unexpected live/segment layout')
    own = p[:, :3]
    shared = (np.asarray(arrays['live']) == 1) & (np.asarray(arrays['segment']) >= 0) & np.isfinite(t)
    ball_known = np.isfinite(ball[:, :3]).all(axis=1)
    own_known = np.isfinite(own[:, :, :3]).all(axis=(1, 2)) & ~(own[:, :, 7] == 1).any(axis=1)
    tied = own[:, :, 1] == np.min(own[:, :, 1], axis=1)[:, None]
    rows = []
    for slot, identity in enumerate(ids[:3]):
        v = own[:, slot]
        valid = (shared & np.isfinite(v[:, :7]).all(axis=1) & (v[:, 7] != 1)
                 & (v[:, 6] >= 0) & (v[:, 6] <= 255))
        credit = tied[:, slot] / np.maximum(tied.sum(axis=1), 1)
        measures = {
            'last_man_share': (credit, valid & own_known),
            'own_goal_depth': (v[:, 1] + 5120., valid),
            'own_third_depth': (v[:, 1] + 5120., valid & ball_known & (ball[:, 1] < -1706.67)),
            'boost_mean': (v[:, 6] / 255., valid),
            'supersonic_share': (np.linalg.norm(v[:, 3:6], axis=1) >= 2200., valid),
            'ball_proximity_share': (np.linalg.norm(v[:, :3] - ball[:, :3], axis=1) <= 1000., valid & ball_known),
            'aerial_share': (v[:, 2] > 300., valid),
            'rotation_back_speed': (-v[:, 4], valid & (v[:, 4] < 0)),
        }
        row = {k: meta[k] for k in ('replay_id', 'series_id', 'season', 'split', 'roster_id')}
        row.update(identity_id=identity, live_seconds=float(valid.sum()/fps),
                   unknown_demolition_samples=int(np.sum(valid & ~np.isfinite(v[:, 7]))))
        for habit, (values, mask) in measures.items():
            seconds = float(mask.sum()/fps)
            row[habit] = float(np.mean(values[mask])) if seconds >= MIN_SECONDS else np.nan
            row[habit + '_seconds'] = seconds
        rows.append(row)
    return rows


def aggregate_games(games):
    check_rows(games)
    if games.duplicated(['identity_id', 'replay_id']).any():
        raise ValueError('Duplicate player-replay features')
    grouped = games.groupby(KEYS, sort=True)
    cells = grouped[list(HABITS)].mean()
    for habit in HABITS:
        cells[habit + '_n'] = grouped[habit].count()
    return cells.reset_index()


def season_means(cells, habit):
    work = cells[KEYS + [habit, habit + '_n']].copy()
    work['total'] = work[habit].fillna(0) * work[habit + '_n']
    summary = work.groupby(['identity_id', 'season'])[['total', habit + '_n']].sum()
    summary[habit] = summary.total / summary[habit + '_n'].replace(0, np.nan)
    return summary.reset_index()


def pair_means(cells, habit, before, after, history):
    if (before, after) not in list(zip(ALLOWED_SEASONS[:-1], ALLOWED_SEASONS[1:])):
        raise ValueError('Only consecutive development seasons are permitted')
    means = season_means(cells, habit)
    valid = means[(means[habit + '_n'] >= MIN_REPLAYS) & np.isfinite(means[habit])]
    left = valid[valid.season == before][['identity_id', habit]].rename(columns={habit: 'x'})
    right = valid[valid.season == after][['identity_id', habit]].rename(columns={habit: 'y'})
    pair = left.merge(right, on='identity_id', validate='one_to_one').sort_values('identity_id')
    groups = []
    for identity in pair.identity_id:
        a, b = history.get((identity, before), {}), history.get((identity, after), {})
        if not a or not b:
            raise ValueError('Missing roster history for eligible player-season')
        groups.append('mixed' if len(a) != 1 or len(b) != 1 else
                      ('same' if next(iter(a.values())) == next(iter(b.values())) else 'changed'))
    return pair.assign(roster_group=groups)


def rho_many(x, y):
    """Average ranks with ties, along the last axis; batch bootstrap friendly."""
    rx, ry = rankdata(x, axis=-1), rankdata(y, axis=-1)
    rx, ry = rx - rx.mean(axis=-1, keepdims=True), ry - ry.mean(axis=-1, keepdims=True)
    denominator = np.sqrt(np.sum(rx**2, axis=-1) * np.sum(ry**2, axis=-1))
    return np.divide(np.sum(rx*ry, axis=-1), denominator,
                     out=np.full(np.shape(denominator), np.nan), where=denominator > 0)


def icc21(values):
    """Absolute-agreement, single-measure, two-way random ICC; batch (..., n, k)."""
    a = np.asarray(values, dtype=float)
    n, k = a.shape[-2:]
    if n < 2 or k < 2:
        return np.full(a.shape[:-2], np.nan)
    grand = a.mean(axis=(-2, -1), keepdims=True)
    target, occasion = a.mean(axis=-1, keepdims=True), a.mean(axis=-2, keepdims=True)
    ms_target = k * np.sum((target-grand)**2, axis=(-2, -1))/(n-1)
    ms_occasion = n * np.sum((occasion-grand)**2, axis=(-2, -1))/(k-1)
    ms_error = np.sum((a-target-occasion+grand)**2, axis=(-2, -1))/((n-1)*(k-1))
    denominator = ms_target + (k-1)*ms_error + k*(ms_occasion-ms_error)/n
    return np.divide(ms_target-ms_error, denominator,
                     out=np.full(a.shape[:-2], np.nan), where=denominator != 0)


def interval(draws, requested):
    good = np.asarray(draws)[np.isfinite(draws)]
    enough = requested > 0 and len(good) >= np.ceil(REQUIRED_VALID_FRACTION*requested)
    return dict(ci95=np.quantile(good, [.025, .975]).tolist() if enough else None,
                valid_bootstrap=int(len(good)), requested_bootstrap=requested)


def bootstrap_stats(x, y, reps, rng):
    # Bounded batches avoid allocating a replicas-by-large-population cube.
    rhos, iccs = [], []
    for offset in range(0, reps, 128):
        index = rng.integers(len(x), size=(min(128, reps-offset), len(x)))
        bx, by = x[index], y[index]
        rho = rho_many(bx, by)
        icc = icc21(np.stack([bx, by], axis=-1))
        rhos.extend(rho)
        iccs.extend(np.where(np.isfinite(rho), icc, np.nan))
    return np.asarray(rhos), np.asarray(iccs)


def stability(pair, reps, permutations, rng):
    empty = np.full(reps, np.nan)
    report = dict(n_players=len(pair), status='insufficient_data', rho=None, icc21=None, p_value=None)
    if len(pair) < MIN_PLAYERS:
        report['reason'] = 'below_fixed_player_minimum'
        return report, empty, empty.copy()
    x, y = pair.x.to_numpy(float), pair.y.to_numpy(float)
    rho = float(rho_many(x, y))
    if not np.isfinite(rho):
        report.update(status='undefined', reason='constant_season_margin')
        return report, empty, empty.copy()
    br, bi = bootstrap_stats(x, y, reps, rng)
    rx, ry = rankdata(x), rankdata(y)
    rx, ry = rx-rx.mean(), ry-ry.mean()
    denominator = np.linalg.norm(rx)*np.linalg.norm(ry)
    exceed = sum(abs(float(rx @ rng.permutation(ry)/denominator)) >= abs(rho)-1e-12
                 for _ in range(permutations))
    report.update(status='fit', rho=rho, icc21=float(icc21(np.column_stack([x, y]))),
                  rho_uncertainty=interval(br, reps), icc21_uncertainty=interval(bi, reps),
                  p_value=(1+exceed)/(permutations+1) if permutations else None,
                  permutations=permutations)
    return report, br, bi


def retention(pair, reps, rng):
    same, sr, _ = stability(pair[pair.roster_group == 'same'], reps, 0, rng)
    changed, cr, _ = stability(pair[pair.roster_group == 'changed'], reps, 0, rng)
    result = dict(status='insufficient_data', same=same, changed=changed,
                  excluded_mixed_roster=int((pair.roster_group == 'mixed').sum()),
                  delta=None, ratio=None, p_value=None)
    if same['status'] != 'fit' or changed['status'] != 'fit':
        return result
    delta = changed['rho'] - same['rho']
    delta_draws = cr-sr
    uncertainty = interval(delta_draws, reps)
    finite = delta_draws[np.isfinite(delta_draws)]
    p = ((1+np.sum(np.abs(finite-delta) >= abs(delta)-1e-12))/(len(finite)+1)
         if uncertainty['ci95'] is not None else None)
    ratio = changed['rho']/same['rho'] if same['rho'] != 0 else None
    ratio_draws = np.divide(cr, sr, out=np.full(reps, np.nan), where=sr != 0)
    ratio_uncertainty = interval(ratio_draws, reps)
    same_ci = same['rho_uncertainty']['ci95']
    weak = same['rho'] <= 0 or same_ci is None or same_ci[0] <= 0
    if weak:
        ratio_uncertainty['ci95'] = None
    result.update(status='fit', delta=delta, ratio=ratio, p_value=float(p) if p is not None else None,
                  delta_uncertainty=uncertainty, ratio_uncertainty=ratio_uncertainty,
                  ratio_status='weak_denominator' if weak else 'estimable')
    return result


def bh_fixed(p_values):
    """Unavailable hypotheses remain in the frozen family as p=1."""
    p = np.array([1. if v is None or not np.isfinite(v) else v for v in p_values])
    order = np.argsort(p, kind='stable')
    adjusted = np.minimum.accumulate((p[order]*len(p)/np.arange(1, len(p)+1))[::-1])[::-1]
    result = np.empty(len(p))
    result[order] = np.minimum(adjusted, 1.)
    return [None if v is None or not np.isfinite(v) else float(q) for v, q in zip(p_values, result)]


def covariance_design_rank(frame):
    """Gram of I, Z_player Z_player', Z_roster Z_roster', without dense n² arrays."""
    n = len(frame)
    pp = float(np.sum(frame.groupby('identity_id').size().to_numpy()**2))
    rr = float(np.sum(frame.groupby('roster_id').size().to_numpy()**2))
    pr = float(np.sum(frame.groupby(['identity_id', 'roster_id']).size().to_numpy()**2))
    gram = np.array([[n, n, n], [n, pp, pr], [n, pr, rr]], float)
    scale = np.sqrt(np.diag(gram))
    return int(np.linalg.matrix_rank(gram / np.outer(scale, scale)))


def fit_variances(frame, crossed):
    attempts = []
    for method in ('lbfgs', 'powell'):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            try:
                if crossed:
                    model = mixedlm('value ~ C(season)', frame, groups=np.ones(len(frame)),
                                    re_formula='0', vc_formula={'player': '0 + C(identity_id)',
                                                              'roster': '0 + C(roster_id)'}, use_sparse=True)
                else:
                    model = mixedlm('value ~ C(season)', frame, groups='identity_id', re_formula='1')
                fit = model.fit(reml=True, method=method, maxiter=1000, disp=False)
                components = (dict(zip(model.exog_vc.names, map(float, fit.vcomp))) if crossed
                              else {'player': float(np.asarray(fit.cov_re)[0, 0])})
                components['residual'] = float(fit.scale)
                usable = bool(fit.converged and np.isfinite(fit.llf)
                              and all(np.isfinite(v) and v >= 0 for v in components.values())
                              and sum(components.values()) > 0)
                diagnostic = dict(optimizer=method, converged=bool(fit.converged),
                                  log_likelihood=float(fit.llf), usable=usable)
            except (ValueError, np.linalg.LinAlgError, RuntimeError, ZeroDivisionError) as exc:
                usable = False
                diagnostic = dict(optimizer=method, error=str(exc), usable=False)
            diagnostic['warnings'] = [str(w.message) for w in caught]
        attempts.append(diagnostic)
        if usable:
            total = sum(components.values())
            return dict(status='fit', variance=components,
                        shares={k: v/total for k, v in components.items()},
                        boundary=any(v/total < 1e-6 for v in components.values()), attempts=attempts)
    return dict(status='failed', attempts=attempts)


def variance_decomposition(cells, habit):
    frame = cells.loc[(cells[habit + '_n'] >= MIN_REPLAYS) & np.isfinite(cells[habit]), KEYS + [habit]].copy()
    frame = frame.rename(columns={habit: 'value'})
    counts = dict(cells=len(frame), players=frame.identity_id.nunique(), rosters=frame.roster_id.nunique(),
                  seasons=frame.season.nunique(),
                  switchers=int((frame.groupby('identity_id').roster_id.nunique() > 1).sum()))
    result = dict(status='unavailable', counts=counts, fallback=None)
    base = counts['cells'] >= MIN_CELLS and counts['players'] >= MIN_MODEL_PLAYERS and counts['seasons'] >= 2
    if not base or frame.value.nunique() < 2:
        result['reason'] = 'insufficient_cells_players_seasons_or_constant_habit'
        return result
    rank = covariance_design_rank(frame)
    result['covariance_design_rank'] = rank
    supported = counts['rosters'] >= MIN_ROSTERS and counts['switchers'] >= MIN_SWITCHERS and rank == 3
    if supported:
        fit = fit_variances(frame, crossed=True)
        result['primary'] = fit
        if fit['status'] == 'fit':
            result['status'] = 'fit'
            return result
    result['reason'] = 'crossed_fit_failed' if supported else 'insufficient_crossed_design_support'
    if (frame.groupby('identity_id').size() > 1).any():
        result['fallback'] = dict(label='descriptive_player_only_roster_unseparated',
                                  roster_variance=None, **fit_variances(frame, crossed=False))
    return result


def analyze(cells, history, bootstrap=BOOTSTRAP, permutations=PERMUTATIONS, seed=SEED):
    if not set(cells.season).issubset(ALLOWED_SEASONS):
        raise ValueError('Forbidden season in aggregate cells')
    results = []
    for transition, (before, after) in enumerate(zip(ALLOWED_SEASONS[:-1], ALLOWED_SEASONS[1:])):
        habits = []
        for j, habit in enumerate(HABITS):
            pair = pair_means(cells, habit, before, after, history)
            # Independent streams make results insensitive to fitting/skipped endpoints.
            overall, _, _ = stability(pair, bootstrap, permutations,
                                     np.random.default_rng(np.random.SeedSequence([seed, transition, j, 0])))
            comparison = retention(pair, bootstrap,
                                   np.random.default_rng(np.random.SeedSequence([seed, transition, j, 1])))
            means = season_means(cells, habit)
            season_counts = {s: dict(observed_players=int((means.season == s).sum()),
                                    eligible_players=int(((means.season == s) &
                                        (means[habit + '_n'] >= MIN_REPLAYS) & np.isfinite(means[habit])).sum()))
                             for s in (before, after)}
            habits.append(dict(habit=habit, eligibility_by_season=season_counts,
                               overall=overall, retention=comparison))
        for endpoint in ('overall', 'retention'):
            q_values = bh_fixed([row[endpoint]['p_value'] for row in habits])
            for row, q in zip(habits, q_values):
                row[endpoint]['q_value'] = q
        results.append(dict(before=before, after=after, habits=habits))
    return dict(transitions=results,
                variance={habit: variance_decomposition(cells, habit) for habit in HABITS})


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.generic):
        return clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, default=DEFAULT_COMPACT)
    parser.add_argument('--output-dir', type=Path, default=Path('results/rq4_habits'))
    parser.add_argument('--prereg', type=Path, default=Path('docs/RQ4_habits_prereg.md'))
    parser.add_argument('--max-replays', type=int, help='Extraction smoke only; skips inference')
    args = parser.parse_args(argv)
    if args.max_replays is not None and args.max_replays <= 0:
        parser.error('--max-replays must be positive')
    started = time.perf_counter()
    spec_hash = hashlib.sha256(args.prereg.read_bytes()).hexdigest()
    pairs, audit = metadata_inventory(guard_path(args.compact))
    history = validate_pairs(pairs)
    validate_offsets(pairs, audit['schema'])
    inventory_seconds = time.perf_counter()-started
    selected = pairs
    rows = []
    extraction_start = time.perf_counter()
    if args.max_replays is not None:
        buckets = {s: sorted([p for p in pairs if p[0]['season'] == s],
                              key=lambda p: (p[0]['_shard'], int(p[0]['start']))) for s in ALLOWED_SEASONS}
        selected = []
        while len(selected) < args.max_replays and any(buckets.values()):
            for season in ALLOWED_SEASONS:
                if buckets[season] and len(selected) < args.max_replays:
                    selected.append(buckets[season].pop(0))
        for pair in selected:
            for meta in pair:
                rows.extend(game_habits(meta, read_slice(meta)))
    else:
        by_shard = defaultdict(list)
        for pair in selected:
            for meta in pair:
                by_shard[meta['_shard']].append(meta)
        for shard, metadata in sorted(by_shard.items()):
            # All metadata validated before any full payload, one shard at a time.
            with np.load(guard_path(shard), allow_pickle=False) as archive:
                arrays = {key: archive[key] for key in REQUIRED}
            for meta in metadata:
                start, stop = int(meta['start']), int(meta['stop'])
                if any(not 0 <= start < stop <= len(a) for a in arrays.values()):
                    raise ValueError('Invalid replay slice bounds')
                rows.extend(game_habits(meta, {k: a[start:stop] for k, a in arrays.items()}))
            del arrays
            print(f'Processed {shard}: {len(rows)} player-replay rows', flush=True)
    feature_seconds = time.perf_counter()-extraction_start
    games = pd.DataFrame(rows)
    if games.empty:
        raise ValueError('No player-replay rows')
    cells = aggregate_games(games)
    inference_start = time.perf_counter()
    result = analyze(cells, history) if args.max_replays is None else {'status': 'smoke_no_inference'}
    inference_seconds = time.perf_counter()-inference_start
    sources = []
    for shard in sorted(audit['schema']):
        p = guard_path(shard)
        meta = guard_path(p.with_suffix('.parquet'))
        sources.append(dict(path=str(p), bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns,
                            metadata_path=str(meta), metadata_sha256=hashlib.sha256(meta.read_bytes()).hexdigest()))
    result.update(analysis='RQ4 interpretable habit stability and teammate-change retention',
                  mode='full' if args.max_replays is None else 'smoke', test_opened=False,
                  development_seasons=list(ALLOWED_SEASONS), habits=list(HABITS),
                  prereg_path=str(args.prereg), prereg_sha256=spec_hash,
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  extraction_sha256=hashlib.sha256(guard_path(args.compact/'extraction.json').read_bytes()).hexdigest(),
                  input_files=sources, available_replays=len(pairs), processed_replays=len(selected),
                  replay_ids=[p[0]['replay_id'] for p in selected], player_replays=len(games),
                  player_replays_by_season=games.groupby('season').size().to_dict(),
                  missing_player_replay_measures=games[list(HABITS)].isna().sum().to_dict(),
                  unknown_demolition_samples=int(games.unknown_demolition_samples.sum()),
                  complete_series_certified=audit['complete_series_certified'],
                  bootstrap=BOOTSTRAP, permutations=PERMUTATIONS, seed=SEED,
                  timings_seconds=dict(inventory=inventory_seconds, features=feature_seconds,
                                       inference=inference_seconds, total=time.perf_counter()-started))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    games.to_parquet(args.output_dir/'player_replays.parquet', index=False)
    cells.to_parquet(args.output_dir/'player_season_roster.parquet', index=False)
    history_rows = [dict(identity_id=p, season=s, roster_id=r, teammates=sorted(teammates))
                    for (p, s), rosters in sorted(history.items()) for r, teammates in sorted(rosters.items())]
    (args.output_dir/'roster_history.json').write_text(json.dumps(history_rows, indent=2)+'\n')
    (args.output_dir/'rq4_habits.json').write_text(json.dumps(clean_json(result), indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(args.output_dir), timings_seconds=result['timings_seconds'])))


if __name__ == '__main__':
    main()
