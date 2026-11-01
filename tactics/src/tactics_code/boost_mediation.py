"""P6.4: descriptive decomposition, not causal mediation.

Frozen P4 initiation -> focal-team boost at baseline + 3 s -> any concession
in (baseline, baseline + 20 s]. Thresholds/vocabulary use TRAIN; regressions
use 2025 validation only. Run as a module in the repo, or as a file with the
reference repo's src on PYTHONPATH. No network or scheduler operations.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile

import numpy as np
import pandas as pd
from scipy import linalg, stats
from threadpoolctl import threadpool_limits

from tactics_code import pushup_dr as dr, pushup_possession as possession

LABEL = 'descriptive decomposition, not causal mediation'
BOOTSTRAP, SEED = 2000, 42
BOOST_DELAY, HORIZON, MAX_GAP = 3., 20., .160001
METRICS = ('a', 'b', 'a*b', 'direct', 'total', 'proportion')
BOOST_COLUMNS = [f'{team}{i}_boost' for team in ('own', 'opp') for i in range(3)]


def _lowmem_log(stage, **dimensions):
    print(json.dumps({'lowmem_stage': stage, **dimensions}), file=sys.stderr, flush=True)


def check_records(records):
    """Enforce season/split pairs before any array read, including helper calls."""
    for row in records:
        season, split = row.get('season'), row.get('split')
        expected = 'val' if season == dr.VAL_SEASON else 'train'
        if season not in dr.ALLOWED_SEASONS or split != expected:
            raise ValueError('Refuse held-out 2026/test, unknown season, or season/split mismatch')
        if '_shard' in row:
            dr.guard_path(row['_shard'])


def validate_frame(df):
    check_records(df[['season', 'split']].drop_duplicates().to_dict('records'))
    if df['series_id'].isna().any() or df['series_id'].astype(str).eq('').any():
        raise ValueError('Known whole-series identifiers required')
    if (df.groupby('series_id')['split'].nunique() > 1).any():
        raise ValueError('Series crosses train/validation')


def future_team_boost(a, indices, goals, replay):
    """Interpolate the three own-player boost tracks at t+3; never a reset.

    Continuous live baseline segment and finite endpoint values are required.
    Known demolition at either endpoint, intervening goal, native/compact gap,
    or unavailable endpoint makes M missing. Missing M is never zero-filled.
    """
    t = np.asarray(a['time'], float)
    if not len(t) or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Invalid compact timeline')
    ii = np.asarray(indices, int)
    if np.any(ii < 0) or np.any(ii >= len(t)):
        raise ValueError('Invalid baseline index')
    p = np.asarray(a['players'])
    gt = np.sort(goals['time'].to_numpy(float))
    gaps0 = np.asarray(json.loads(replay.get('gap_start_times', '[]')), float)
    gaps1 = np.asarray(json.loads(replay.get('gap_end_times', '[]')), float)
    values = np.full(len(ii), np.nan)
    reasons = []
    for k, i in enumerate(ii):
        end = t[i] + BOOST_DELAY
        right = int(np.searchsorted(t, end))
        if right == len(t):
            reasons.append('endpoint_unobserved')
            continue
        left = right if abs(t[right]-end) < 1e-7 else right-1
        span = slice(i, right+1)
        first = np.searchsorted(gt, t[i], side='right')
        if first < len(gt) and gt[first] <= end + 1e-7:
            reasons.append('goal_before_or_at_boost')
        elif (left < i or not np.all(a['live'][span]) or
              not np.all(a['segment'][span] == a['segment'][i]) or a['segment'][i] < 0 or
              np.any(np.diff(t[span]) > MAX_GAP) or
              np.any((gaps0 < end) & (gaps1 > t[i]))):
            reasons.append('gap_or_live_segment_change')
        elif (not np.isfinite(p[[left, right], :3, 6]).all() or
              np.any(p[[left, right], :3, 7] == 1)):
            reasons.append('invalid_team_boost_endpoint')
        else:
            endpoint = p[left, :3, 6] if left == right else (
                p[left, :3, 6] + (p[right, :3, 6]-p[left, :3, 6]) *
                ((end-t[left])/(t[right]-t[left])))
            values[k] = endpoint.mean()
            reasons.append('observed')
    return values, reasons


def concede_labels(times, focal_team, goals, replay):
    """Any opponent goal in (t,t+20], including after a focal-team goal.

    A known concession establishes the binary outcome even in a partial tail.
    A zero requires continuous native coverage to deadline or verified game end.
    """
    gt = np.sort(goals.loc[goals['scoring_team'] != focal_team, 'time'].to_numpy(float))
    gaps0 = np.asarray(json.loads(replay.get('gap_start_times', '[]')), float)
    gaps1 = np.asarray(json.loads(replay.get('gap_end_times', '[]')), float)
    terminal = replay.get('terminal_time')
    stop = float(terminal) if replay.get('terminal_verified', False) and pd.notna(terminal) else np.inf
    result = np.full(len(times), np.nan)
    for k, t in enumerate(times):
        deadline = min(t + HORIZON, stop)
        if deadline < t:
            continue
        j = np.searchsorted(gt, t, side='right')
        if j < len(gt) and gt[j] <= deadline + 1e-7:
            result[k] = 1.
        elif (deadline <= float(replay['observed_end_time']) + 1e-7 and
              not np.any((gaps0 < deadline) & (gaps1 > t))):
            result[k] = 0.
    return result


def anchor_shard(shard, records, goals, by_replay, artifacts, smoke, scratch):
    check_records(records)
    chunks, counts = [], Counter()
    with tempfile.TemporaryDirectory(prefix='p6-boost-', dir=scratch or artifacts) as work:
        arrays = None
        if not smoke:
            directory = Path(dr.unpack_shard(dr.guard_path(shard), Path(work)))
            with zipfile.ZipFile(dr.guard_path(shard)) as archive:
                with archive.open('touch.npy') as source, (directory/'touch.npy').open('wb') as target:
                    shutil.copyfileobj(source, target)
            arrays = {key: np.load(directory/(key+'.npy'), mmap_mode='r', allow_pickle=False)
                      for key in dr.REQUIRED | {'touch'}}
        for meta in records:
            if smoke:
                a = dr.read_slice(meta)
                a['touch'] = possession.read_touch_slice(meta)
            else:
                a = {key: value[int(meta['start']):int(meta['stop'])] for key, value in arrays.items()}
            rid = meta['replay_id']
            gg, replay = goals[goals['replay_id'] == rid], dict(by_replay[rid], replay_id=rid)
            frame, audit = dr.anchors_for_replay(meta, a, gg, replay, SEED, spacing=1., design='initiation')
            counts.update(audit)
            if frame.empty:
                continue
            ii = np.searchsorted(a['time'], frame['state_time'].to_numpy())
            if not np.array_equal(a['time'][ii], frame['state_time'].to_numpy()):
                raise ValueError('Baseline must match exact compact timestamp')
            frame = pd.concat([frame.reset_index(drop=True), possession.possession_features(a, ii)], axis=1)
            frame['boost_t3_raw'], frame['boost_status'] = future_team_boost(a, ii, gg, replay)
            frame['concede20'] = concede_labels(frame['state_time'].to_numpy(), int(meta['focal_team']), gg, replay)
            counts.update({'boost_'+key: value for key, value in Counter(frame['boost_status']).items()})
            chunks.append(frame)
    return chunks, counts


def build_anchors(pairs, goals, replays, artifacts, smoke=False, scratch=None, workers=1):
    selected = [row for pair in pairs for row in pair]
    check_records(selected)
    by_shard = defaultdict(list)
    for row in selected:
        by_shard[row['_shard']].append(row)
    by_replay = replays.set_index('replay_id').to_dict('index')
    tasks = [(shard, rows, goals[goals['replay_id'].isin({r['replay_id'] for r in rows})],
              by_replay, artifacts, smoke, scratch) for shard, rows in sorted(by_shard.items())]
    frames, counts = [], Counter()
    for chunks, audit in dr.parallel_tasks(anchor_shard, tasks, workers):
        frames.extend(chunks)
        counts.update(audit)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), dict(counts)


def freeze_boost_scale(df):
    """TRAIN-only repeated saturation distinguishes byte and percentage scales.

    Low-range samples cannot identify units: fail rather than guessing from a
    maximum below full scale. Mixed encodings cannot always be detected by range.
    """
    validate_frame(df)
    train = df[df['split'] == 'train']
    raw = train[BOOST_COLUMNS].to_numpy(float)
    finite = raw[np.isfinite(raw)]
    if not len(finite) or finite.min() < 0 or finite.max() > 255 + 1e-5:
        raise ValueError('Missing or out-of-range training boost')
    scale = 255. if finite.max() > 100 + 1e-5 else 100.
    saturated = np.isclose(raw, scale, atol=1e-5, rtol=0)
    saturation_series = train.loc[saturated.any(axis=1), 'series_id'].nunique()
    if saturated.sum() < 2 or saturation_series < 2:
        raise ValueError('Ambiguous boost scale: repeated TRAIN saturation in distinct series required')
    return scale, {'label': LABEL, 'fit_split': 'train', 'fit_seasons': list(dr.TRAIN_SEASONS),
                   'raw_scale': scale, 'raw_minimum': finite.min(), 'raw_maximum': finite.max(),
                   'saturation_values': int(saturated.sum()), 'saturation_series': int(saturation_series),
                   'output_units': 'boost percentage points', 'multiplier': 100./scale,
                   'schema': 'data.PLAYER_COLUMNS -> extract_replay -> players[:, :3, 6]; raw units unchanged'}


def normalize_boost(df, scale):
    result = df.copy()
    for column in BOOST_COLUMNS + ['boost_t3_raw']:
        values = result[column].to_numpy(float)
        finite = values[np.isfinite(values)]
        if len(finite) and (finite.min() < 0 or finite.max() > scale + 1e-5):
            raise ValueError('Boost outside frozen TRAIN scale; refuse to rescale validation')
    result['boost_t3'] = result['boost_t3_raw'] * (100./scale)
    # Baseline controls stay in the possession model's raw units; a nonsingular
    # rescaling would not change their adjusted linear-model column space.
    return result


def _solve_psd(matrix, rhs):
    try:
        return linalg.cho_solve(linalg.cho_factor(matrix, check_finite=False), rhs, check_finite=False)
    except linalg.LinAlgError:
        return linalg.pinvh(matrix, rtol=1e-10, check_finite=False) @ rhs


def _coefficients(moment, q):
    """Refit all controls using the exact resampled whole-series moments."""
    residual = moment[q:, q:] - moment[:q, q:].T @ _solve_psd(moment[:q, :q], moment[:q, q:])
    va, am, ay = residual[0, :]
    if va <= 1e-10:
        raise ValueError('Indicator not identifiable after covariate adjustment')
    a, total = am/va, ay/va
    vm = residual[1, 1] - am*am/va
    if vm <= 1e-10:
        raise ValueError('Boost not identifiable after indicator/covariate adjustment')
    b = (residual[1, 2]-am*ay/va)/vm
    product = a*b
    return np.array([a, b, product, total-product, total,
                     product/total if abs(total) > 1e-10 else np.nan])


def _cr1(moments, q, n, point, *, lowmem=False):
    """Joint series sandwich for a,b,direct,total; delta method for products."""
    g = len(moments)
    total = moments.sum(axis=0)
    amodel, bmodel = list(range(q+1)), list(range(q+2))
    scores = []
    for columns, outcome, target in ((amodel, q+1, q), (bmodel, q+2, q+1),
                                      (bmodel, q+2, q), (amodel, q+2, q)):
        h = total[np.ix_(columns, columns)]
        inverse = _solve_psd(h, np.eye(len(columns)))
        beta = inverse @ total[columns, outcome]
        # Both model designs are contiguous prefixes. A view avoids two G*q*q
        # advanced-index copies while retaining the same score contraction.
        block = (moments[:, :len(columns), :len(columns)] if lowmem else
                 moments[:, columns][:, :, columns])
        score = moments[:, columns, outcome] - np.einsum('gij,j->gi', block, beta)
        del block
        factor = np.sqrt(g/(g-1) * (n-1)/(n-len(columns)))
        scores.append((score @ inverse[:, columns.index(target)]) * factor)
    covariance = np.cov(np.asarray(scores), bias=True) * g
    a, b, product, direct, total_value, proportion = point
    jacobian = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [b, a, 0, 0],
                         [0, 0, 1, 0], [0, 0, 0, 1],
                         [b/total_value, a/total_value, 0, -product/total_value**2]
                         if np.isfinite(proportion) else [np.nan]*4])
    variance = np.einsum('ij,jk,ik->i', jacobian, covariance, jacobian)
    return np.sqrt(np.maximum(variance, 0))


def fit_decomposition(indicator, boost, outcome, controls, series, *, repeats=BOOTSTRAP, seed=SEED, lowmem=False):
    """Equal-series weighted OLS/LPM with paired whole-series refits and CR1.

    Each draw samples G complete clusters with replacement. An occurrence keeps
    all its rows at weight 1/n_g, including both team perspectives and all games.
    Sufficient statistics are an exact compression, not a frozen-fit bootstrap.
    """
    started = time.perf_counter()
    a, m, y = [np.asarray(x, float) for x in (indicator, boost, outcome)]
    x = np.asarray(controls, float)
    series = np.asarray(series).astype(str)
    n = len(a)
    if x.ndim != 2 or len(x) != n or len(m) != n or len(y) != n or len(series) != n:
        raise ValueError('Inconsistent model dimensions')
    finite = (all(np.isfinite(value).all() for value in (a, m, y, x)) if lowmem else
              np.isfinite(np.column_stack([a, m, y, x])).all())
    if not finite or not np.isin(a, [0, 1]).all():
        raise ValueError('Finite complete cases and binary indicator required')
    if not np.isin(y, [0, 1]).all():
        raise ValueError('Concede outcome must be binary')
    ids, codes = np.unique(series, return_inverse=True)
    g = len(ids)
    if g < 2 or repeats < 1:
        raise ValueError('Multiple series and positive bootstrap repetitions required')
    # QR removes only redundant nuisance columns. It never drops A or M.
    c = np.column_stack([np.ones(n), x])
    if lowmem:
        _lowmem_log('qr', rows=n, controls=x.shape[1], design_bytes=c.nbytes)
        # raw uses the identical pivoted GEQP3 factorization as economic, but
        # skips explicit Q. mode='r' would still return an n-by-p padded R.
        reflectors, r, pivots = linalg.qr(c, mode='raw', pivoting=True, check_finite=False)
        del reflectors
    else:
        _, r, pivots = linalg.qr(c, mode='economic', pivoting=True, check_finite=False)
    rank = int(np.count_nonzero(np.abs(np.diag(r)) > np.abs(r[0, 0])*1e-10))
    keep = np.sort(pivots[:rank])
    c = c[:, keep]
    q = c.shape[1]
    if n <= q+2:
        raise ValueError('Insufficient residual degrees of freedom')
    z = np.column_stack([c, a, m, y])
    if lowmem:
        del c
        _lowmem_log('moments', rows=n, series=g, rank=q,
                    moments_bytes=8*g*z.shape[1]**2, design_bytes=z.nbytes)
    moments = np.empty((g, z.shape[1], z.shape[1]))
    for i in range(g):
        part = z[codes == i]
        moments[i] = (part.T @ part)/len(part)
    if lowmem:
        del z, part
    point = _coefficients(moments.sum(axis=0), q)
    se = _cr1(moments, q, n, point, lowmem=lowmem)
    preparation_seconds = time.perf_counter()-started
    rng = np.random.default_rng(seed)
    draws = np.full((repeats, len(METRICS)), np.nan)
    failures = Counter()
    clock = time.perf_counter()
    flat = moments.reshape(g, -1)
    if lowmem:
        _lowmem_log('bootstrap', repeats=repeats, series=g, moments_bytes=moments.nbytes,
                    draws_bytes=draws.nbytes)
    for rep in range(repeats):
        counts = np.bincount(rng.integers(g, size=g), minlength=g)
        moment = (counts @ flat).reshape(moments.shape[1:])
        try:
            draws[rep] = _coefficients(moment, q)
        except ValueError as exc:
            failures[str(exc)] += 1
    bootstrap_seconds = time.perf_counter()-clock
    metrics = {}
    critical = stats.t.ppf(.975, g-1)
    total_interval = np.quantile(draws[:, 4], [.025, .975]) if np.isfinite(draws[:, 4]).all() else None
    unstable_ratio = total_interval is None or total_interval[0] <= 0 <= total_interval[1]
    for i, name in enumerate(METRICS):
        valid = np.isfinite(draws[:, i])
        interval = np.quantile(draws[:, i], [.025, .975]) if valid.all() else None
        cr1_ci = point[i] + np.array([-1, 1])*critical*se[i]
        if name == 'proportion' and unstable_ratio:
            interval, cr1_ci = None, None
        metrics[name] = {'estimate': point[i], 'bootstrap_ci95': interval, 'cr1_se': se[i],
                         'cr1_ci95': cr1_ci, 'valid_bootstrap_replicates': int(valid.sum()),
                         'status': ('unstable_total_near_zero' if name == 'proportion' and unstable_ratio else
                                    'undefined' if not np.isfinite(point[i]) else
                                    'incomplete_bootstrap' if not valid.all() else 'ok')}
    return {'label': LABEL, 'metrics': metrics, 'rows': n, 'series': g,
            'covariate_rank_including_intercept': q, 'redundant_control_columns': int(x.shape[1]+1-q),
            'retained_control_indices_including_intercept': keep,
            'bootstrap': {'repeats': repeats, 'seed': seed, 'unit': 'whole series',
                          'weighting': 'equal series; all retained rows per sampled occurrence',
                          'refit': 'all regression coefficients; fixed training thresholds and vocabulary',
                          'invalid_draws': dict(failures), 'ci': 'paired percentile; suppress if any draw invalid'},
            'cr1': 'joint series sandwich; equation-specific CR1 correction; t(G-1); delta method for derived metrics',
            'timing_seconds': {'preparation': preparation_seconds, 'bootstrap': bootstrap_seconds,
                               'total': time.perf_counter()-started}}, draws


def analyze(anchors, population='all', *, lowmem=False):
    validate_frame(anchors)
    scale, scale_audit = freeze_boost_scale(anchors)
    normalized = normalize_boost(anchors, scale)
    assigned, thresholds = dr.freeze_initiation(normalized, delta=dr.DEFAULT_DELTA, control='third', include_early=False)
    if lowmem:
        del normalized
    # Freeze using ALL baseline candidates before future-boost/outcome exclusions.
    train_mask = assigned['split'].eq('train').to_numpy()
    if lowmem:
        from tactics_code import lowmem as lowmem_ops
        x, names, regions = lowmem_ops.possession_feature_matrix(assigned, train_mask)
        _lowmem_log('features', rows=len(x), columns=x.shape[1], dtype=str(x.dtype), bytes=x.nbytes)
    else:
        x, names, regions = possession.feature_matrix(assigned, train_mask)
    if not train_mask.any():
        raise ValueError('Training observations required')
    if lowmem:
        center, spread = lowmem_ops.training_moments(x, train_mask)
        _lowmem_log('training_moments', rows=int(train_mask.sum()), columns=x.shape[1])
    else:
        center, spread = x[train_mask].mean(axis=0, dtype=float), x[train_mask].std(axis=0, dtype=float)
    spread = np.where(spread > 1e-10, spread, 1.)
    if not lowmem:
        x = (x-center)/spread
    mask = assigned['split'].eq('val').to_numpy()
    if population != 'all':
        mask = mask & assigned['population'].eq(population).to_numpy()
    candidates = mask.copy()
    mask = mask & assigned['treatment'].notna().to_numpy()
    arms = mask.copy()
    mask = mask & np.isfinite(assigned['boost_t3'].to_numpy(float))
    boost_observed = mask.copy()
    mask = mask & np.isfinite(assigned['concede20'].to_numpy(float))
    rows = assigned.loc[mask].copy()
    if rows.empty:
        raise ValueError('No complete validation rows; no decomposition reported')
    if lowmem:
        controls = lowmem_ops.standardized_rows(x, mask, center, spread)
        del x
        _lowmem_log('complete_case_controls', rows=len(controls), columns=controls.shape[1],
                    dtype=str(controls.dtype), bytes=controls.nbytes)
    else:
        controls = x[mask]
    with threadpool_limits(limits=1):
        result, draws = fit_decomposition(rows['treatment'], rows['boost_t3'], rows['concede20'], controls,
                                         rows['series_id'], lowmem=lowmem)
    result.update(split='val', season=dr.VAL_SEASON, population=population, thresholds=thresholds,
                  boost_scale=scale_audit, feature_names=names, training_region_levels=regions,
                  covariate_center_train=center, covariate_scale_train=spread,
                  row_audit={'validation_candidates': int(candidates.sum()), 'assigned_arms': int(arms.sum()),
                             'boost_observed': int(boost_observed.sum()), 'complete_cases': int(mask.sum()),
                             'boost_missing_by_reason': assigned.loc[arms & ~boost_observed, 'boost_status'].value_counts().to_dict(),
                             'arm_counts': rows['treatment'].value_counts().to_dict(),
                             'concessions': int(rows['concede20'].sum()),
                             'unknown_validation_defenders': int((~rows['last_man_id'].isin(
                                 set(assigned.loc[train_mask, 'last_man_id']))).sum())})
    return result, assigned, draws


def synthetic_fixture(seed=SEED):
    """Known conditional slopes with a binary outcome; calibration only."""
    rng = np.random.default_rng(seed)
    g, size = 120, 200
    n = g*size
    x = rng.uniform(-1, 1, size=(n, 4))
    a = rng.binomial(1, .5 + .15*x[:, 0])
    known = {'a': 8., 'b': .012, 'direct': .035}
    m = 40 + known['a']*a + 3*x[:, 0] + rng.uniform(-15, 15, n)
    probability = .30 + known['direct']*a + known['b']*(m-40) + .04*x[:, 0]
    y = rng.binomial(1, probability)
    return a, m, y, x, np.repeat(np.arange(g), size), known


def self_test():
    a, m, y, x, series, known = synthetic_fixture()
    with threadpool_limits(limits=1):
        result, _ = fit_decomposition(a, m, y, x, series)
    known['a*b'] = known['a']*known['b']
    known['total'] = known['direct']+known['a*b']
    known['proportion'] = known['a*b']/known['total']
    tolerances = {}
    for name in ('a', 'b'):
        # A random calibration sample need not contain the generating value in
        # every nominal interval. A fixed four-SE recovery check avoids seed tuning.
        tolerances[name] = max(4*result['metrics'][name]['cr1_se'], 1e-9)
        if abs(result['metrics'][name]['estimate']-known[name]) > tolerances[name]:
            raise AssertionError(f'Synthetic {name} not recovered')
    result.update(synthetic_only=True, known_coefficients=known, recovery_tolerances=tolerances)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=LABEL)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--compact', type=Path)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--state-map', type=Path)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--lowmem', action='store_true', help='Equivalent allocation-saving analysis path')
    parser.add_argument('--max-replays', type=int)
    parser.add_argument('--population', choices=('all', 'late_trailing'), default='all')
    args = parser.parse_args(argv)
    if args.self_test:
        result = self_test()
        if args.out:
            dr.atomic_json(dr.guard_path(args.out), result)
        from tactics_code.common import clean
        print(json.dumps(clean(result), allow_nan=False))
        return result
    for name in ('compact', 'data_root', 'state_map', 'artifacts', 'out'):
        if getattr(args, name) is None:
            parser.error('--'+name.replace('_', '-')+' is required for replay analysis')
    if args.workers < 1 or args.max_replays is not None and not (1 <= args.max_replays <= 40 and args.workers == 1):
        parser.error('Positive workers; smoke requires at most 40 replays and one worker')
    for name in ('compact', 'data_root', 'state_map', 'artifacts', 'out', 'scratch'):
        if getattr(args, name) is not None:
            setattr(args, name, dr.guard_path(getattr(args, name)).resolve())
    for dest in (args.artifacts, args.out, args.scratch):
        if dest is not None and any(dest == src or src in dest.parents for src in (args.compact, args.data_root)):
            raise ValueError('Outputs must not modify input data trees')
    args.artifacts.mkdir(parents=True, exist_ok=True)
    if args.scratch:
        args.scratch.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    pairs, inventory = dr.metadata_inventory(args.compact)
    pairs = dr.select_pairs(pairs, args.max_replays, seed=SEED)
    selected = [row for pair in pairs for row in pair]
    check_records(selected)
    if not selected:
        raise ValueError('No allowed development replays')
    timing = {'inventory': time.perf_counter()-started}
    dr.atomic_json(args.artifacts/'selected_replays.json', selected)
    clock = time.perf_counter()
    print('phase=events start', file=sys.stderr, flush=True)
    goals, replays = dr.build_events(selected, args.artifacts, data_root=args.data_root, state_map_path=args.state_map)
    timing['events'] = time.perf_counter()-clock
    clock = time.perf_counter()
    print('phase=anchors start', file=sys.stderr, flush=True)
    anchors, audit = build_anchors(pairs, goals, replays, args.artifacts,
                                   args.max_replays is not None, args.scratch, args.workers)
    timing['anchors'] = time.perf_counter()-clock
    if anchors.empty:
        raise ValueError('No eligible anchors')
    clock = time.perf_counter()
    print('phase=analysis start', file=sys.stderr, flush=True)
    result, assigned, draws = analyze(anchors, args.population, lowmem=args.lowmem)
    timing['analysis'] = time.perf_counter()-clock
    assigned.to_parquet(args.artifacts/'anchors.parquet', index=False)
    np.save(args.artifacts/'bootstrap_draws.npy', draws, allow_pickle=False)
    sources = [Path(__file__), Path(dr.__file__), Path(possession.__file__),
               Path(dr.__file__).with_name('events.py'), Path(dr.__file__).with_name('screen.py'),
               Path(dr.__file__).with_name('data.py'), Path(dr.__file__).with_name('extract.py')]
    if args.lowmem:
        sources.append(Path(__file__).with_name('lowmem.py'))
    result.update(task='P6.4', label=LABEL, smoke_only=args.max_replays is not None,
                  test_2026_opened=False, inventory=inventory, anchor_audit=audit,
                  source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  parameters=vars(args), timing_seconds_pipeline=dict(timing, total=time.perf_counter()-started),
                  outcome='Any opponent goal in (baseline t, t+20]; not a first-goal competing category',
                  mediator='Own three-player mean at t+3; continuous live segment, before any intervening goal',
                  caveats=['Complete-case selection includes surviving to observed t+3 in the same live segment.',
                           'Threshold uncertainty is conditional on frozen training data.',
                           'Only available members of each series are present; external completeness is not certified.',
                           'Linear probability coefficients are descriptive; fitted values may leave the probability range.',
                           'Proportion is an algebraic ratio, may leave [0,1], and is unstable near zero total.',
                           'Range checks cannot identify every mixture of raw and percentage encodings.'])
    dr.atomic_json(args.out, result)
    dr.atomic_json(args.artifacts/'boost_mediation.json', result)
    print(json.dumps({'label': LABEL, 'output': str(args.out), 'timing_seconds': result['timing_seconds_pipeline']}))
    return result


if __name__ == '__main__':
    main()
