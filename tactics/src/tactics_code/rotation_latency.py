"""P5a validation-only rotation latency associations; P5b is out of scope."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
import zipfile

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import norm

from .common import atomic_json
from .data import DEFAULT_DATA_ROOT
from .events import build_events, guard_path
from .stats import bootstrap_ols, cluster_ols

# Registered constants: docs/P5_structure_prereg.md, section P5a.
THRESHOLDS = (1500, 1200, 1800)
HORIZON, LATE, N_BOOTSTRAP, PILOT_SERIES, SEED = 10., 60., 2000, 100, 42
VAL_SEASON = 'rlcs-2025'
# Field geometry and gap rule follow extract.py / pressure.py conventions.
GOAL_Y, HALF_WIDTH, GAP_MULTIPLIER = -5120., 4096., 1.75
REQUIRED = {'players', 'ball', 'time', 'live', 'segment', 'touch',
            'remaining', 'score_diff', 'overtime'}
MODELS = ('L1_km_rmst', 'L1_uncensored_ols', 'L2_latency_logit')


def check_val(frame):
    if len(frame) and not (frame.season.eq(VAL_SEASON).all() and frame.split.eq('val').all()):
        raise ValueError('Only validation season/split is allowed')


def inventory(root):
    """Metadata first, only the fixed validation directory; guard every symlink."""
    directory = guard_path(guard_path(root) / VAL_SEASON)
    shards, seen, pairs = [], set(), {}
    for path in sorted(directory.glob('compact-*.parquet')):
        path = guard_path(path)
        numeric = guard_path(path.with_suffix('.npz'))
        frame = pd.read_parquet(path)
        check_val(frame)
        for row in frame.to_dict('records'):
            for key in ('series_id', 'replay_id'):
                if not isinstance(row.get(key), str) or not row[key]:
                    raise ValueError('Known replay and series IDs required')
            key = (row['replay_id'], row['focal_team'])
            if key in seen or row['focal_team'] not in (0, 1):
                raise ValueError('Duplicate or invalid replay perspective')
            seen.add(key)
            pairs.setdefault(row['replay_id'], []).append(row)
            if not all(np.isfinite(row[k]) and int(row[k]) == row[k] for k in ('start', 'stop')) or not 0 <= row['start'] < row['stop']:
                raise ValueError('Invalid compact slice bounds')
            if not np.isfinite(row.get('fps', np.nan)) or row['fps'] <= 0:
                raise ValueError('Positive compact sample frequency required')
        intervals = sorted(zip(frame.start, frame.stop)) if len(frame) else []
        if any(b > c for (_, b), (c, _) in zip(intervals, intervals[1:])):
            raise ValueError('Overlapping compact slices')
        if not numeric.is_file():
            raise ValueError('Missing numeric shard')
        shards.append((path, numeric, frame))
    for rows in pairs.values():
        if len(rows) != 2 or len({r['series_id'] for r in rows}) != 1:
            raise ValueError('Both focal perspectives in the same series required')
    if not pairs:
        raise ValueError('No validation compact metadata')
    return shards


def select_series(shards, pilot):
    ids = sorted({s for _, _, frame in shards for s in frame.series_id})
    if pilot:
        if len(ids) < PILOT_SERIES:
            raise ValueError('Pilot requires the registered count of available series')
        ids = sorted(np.random.default_rng(SEED).choice(ids, PILOT_SERIES, replace=False).tolist())
    return ids


def mapped_shard(shard, directory):
    """P4 possession loader pattern: bounded disk unpack, immutable mmap views."""
    with zipfile.ZipFile(guard_path(shard)) as archive:
        for key in sorted(REQUIRED):
            with archive.open(key + '.npy') as source, (directory / (key + '.npy')).open('wb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
    arrays = {key: np.load(directory / (key + '.npy'), mmap_mode='r', allow_pickle=False)
              for key in REQUIRED}
    if len({len(a) for a in arrays.values()}) != 1:
        raise ValueError('Compact array lengths disagree')
    return arrays


def concession_label(anchor, focal, goals, replay):
    """Any audited opponent goal in (loss, loss+horizon]; unknown stays missing.

    A negative needs a complete native window or a certified terminal. A compact
    stoppage alone does not certify a negative. Brackets crossing either endpoint
    and unobserved native intervals remain unknown.
    """
    if replay is None or replay.get('validated') is not True:
        return np.nan, 'native_replay_unvalidated'
    end = anchor + HORIZON
    valid = goals.loc[goals.validated.eq(True)] if len(goals) else goals
    opponent = valid.loc[valid.scoring_team.ne(focal)] if len(valid) else valid
    if len(opponent):
        known = opponent.time.gt(anchor) & opponent.time.le(end) & opponent.last_live_time.ge(anchor)
        if known.any():
            return 1., 'audited_concession'
        ambiguous = ((opponent.last_live_time.lt(anchor) & opponent.time.gt(anchor)) |
                     (opponent.last_live_time.lt(end) & opponent.time.gt(end)))
        if ambiguous.any():
            return np.nan, 'goal_bracket_crosses_endpoint'
    terminal = replay.get('terminal_time', np.nan)
    certified = replay.get('terminal_verified') is True and pd.notna(terminal) and terminal >= anchor
    observed_end = replay.get('observed_end_time', np.nan)
    required_end = min(end, terminal) if certified else end
    if replay.get('observed_start_time', np.inf) > anchor or not np.isfinite(observed_end) or observed_end < required_end:
        return np.nan, 'incomplete_native_window'
    for left, right in zip(json.loads(replay.get('gap_start_times', '[]')),
                           json.loads(replay.get('gap_end_times', '[]'))):
        if left < required_end and right > anchor:
            return np.nan, 'native_gap'
    return 0., 'complete_native_window'


def replay_losses(meta, arrays, goals, replay):
    """Canonical own-first, attack-positive coordinates; no second rotation.

    Carry last touch only inside a continuous live regulation segment. Distance
    is planar distance to (0, own goal line). Any available, non-demolished own
    player can supply recovery, including at the loss timestamp itself.
    """
    check_val(pd.DataFrame([meta]))
    t = np.asarray(arrays['time'], float)
    n = len(t)
    if n == 0 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Finite strictly increasing compact time required')
    if any(len(a) != n for a in arrays.values()):
        raise ValueError('Mismatched replay arrays')
    players, ball = np.asarray(arrays['players']), np.asarray(arrays['ball'])
    if players.ndim != 3 or players.shape[1] != 6 or players.shape[2] < 8 or ball.ndim != 2 or ball.shape[1] < 3:
        raise ValueError('Unexpected canonical geometry layout')
    touch = np.asarray(arrays['touch'])
    if not np.isin(touch, [-1, 0, 1, 2, 3, 4, 5]).all():
        raise ValueError('Invalid canonical touch slots')
    live = np.asarray(arrays['live']) == 1
    ot, remaining, score, segment = (np.asarray(arrays[k], float) for k in
                                    ('overtime', 'remaining', 'score_diff', 'segment'))
    usable = (live & (ot == 0) & np.isfinite(remaining) & (remaining >= 0)
              & np.isfinite(segment) & (segment >= 0) & (segment == np.floor(segment)))
    max_gap = GAP_MULTIPLIER / float(meta['fps'])
    continuation = np.r_[False, usable[1:] & usable[:-1] & (segment[1:] == segment[:-1])
                         & (np.diff(t) <= max_gap)]
    own = players[:, :3]
    finite_player = np.isfinite(own[:, :, :2]).all(axis=2)
    absent = own[:, :, 7] == 1
    ball_known = np.isfinite(ball[:, 1])
    # Unknown demolition duration is retained as an explicit measurement caveat.
    known_geometry = ball_known & np.all(finite_player | absent, axis=1)
    distance = np.hypot(own[:, :, 0], own[:, :, 1] - GOAL_Y)
    recovery = {radius: ball_known & np.any(finite_player & ~absent & (distance <= radius)
                & (own[:, :, 1] < ball[:, None, 1]), axis=1) for radius in THRESHOLDS}
    records, audit, last_team = [], Counter(), None
    for i in range(n):
        if not continuation[i]:
            last_team = None
        if not usable[i]:
            continue
        if touch[i] < 0:
            continue
        team = int(touch[i] >= 3)
        loss = last_team == 0 and team == 1
        last_team = team
        if not loss:
            continue
        audit['candidate_losses'] += 1
        if not np.isfinite(score[i]) or score[i] != np.floor(score[i]):
            audit['unknown_score_losses'] += 1
            continue
        label, outcome_reason = concession_label(t[i], int(meta['focal_team']), goals, replay)
        audit['outcome_' + outcome_reason] += 1
        opponent_boost = players[i, 3:, 6]
        boost = float(opponent_boost.mean()) if np.isfinite(opponent_boost).all() else np.nan
        baseline = dict(series_id=meta['series_id'], replay_id=meta['replay_id'],
                        focal_team=meta['focal_team'], season=meta['season'], split=meta['split'],
                        loss_time=float(t[i]), score_diff=float(score[i]), remaining=float(remaining[i]),
                        ball_x=float(ball[i, 0]), ball_y=float(ball[i, 1]), opponent_boost=boost,
                        concede10=label, outcome_reason=outcome_reason)
        for radius in THRESHOLDS:
            duration, observed, reason = 0., False, 'end_of_replay'
            for j in range(i, n):
                if j > i and not continuation[j]:
                    # A sampled live exit gives a stoppage timestamp. Hidden
                    # segment changes/gaps only certify the previous live time.
                    ordinary_stop = arrays['live'][j] == 0 and t[j] - t[j-1] <= max_gap
                    boundary = t[j] if ordinary_stop else t[j-1]
                    duration = min(HORIZON, boundary - t[i])
                    reason = 'stoppage' if ordinary_stop else 'gap_or_segment_boundary'
                    break
                elapsed = t[j] - t[i]
                if elapsed > HORIZON:
                    duration, reason = HORIZON, 'horizon'
                    break
                if recovery[radius][j]:
                    duration, observed, reason = elapsed, True, 'recovered'
                    break
                if not known_geometry[j]:
                    duration = 0. if j == i else t[j-1] - t[i]
                    reason = 'missing_geometry'
                    break
                duration = elapsed
                if elapsed == HORIZON:
                    reason = 'horizon'
                    break
            records.append(dict(baseline, threshold=radius, latency=float(duration),
                                recovered=observed, censor_reason=reason))
    return records, audit


def unavailable(reason, data, status='not_estimable'):
    return dict(status=status, reason=reason, estimate=None, ci_low=None, ci_high=None,
                se=None, p_value=None, n_rows=len(data),
                n_series=int(data.series_id.nunique()) if 'series_id' in data else 0,
                series_bootstrap=dict(requested_replicates=N_BOOTSTRAP, successful_replicates=0),
                null_value=0.)


def km_rmst(duration, recovered, weights=None):
    """KM integral; no extrapolation beyond the final at-risk observation.

    If survival reaches zero, its remaining integral is identified as zero.
    Censoring tied with a recovery is removed after the recovery hazard.
    """
    duration, recovered = np.asarray(duration, float), np.asarray(recovered, bool)
    w = np.ones(len(duration)) if weights is None else np.asarray(weights, float)
    keep = w > 0
    duration, recovered, w = duration[keep], recovered[keep], w[keep]
    if not len(w) or np.any(~np.isfinite(duration)) or np.any((duration < 0) | (duration > HORIZON)):
        raise ValueError('No valid KM risk set')
    times, inv = np.unique(duration, return_inverse=True)
    total = np.bincount(inv, weights=w)
    failures = np.bincount(inv, weights=w * recovered, minlength=len(times))
    risk = total[::-1].cumsum()[::-1]
    surv, area, previous = 1., 0., 0.
    for moment, d, r in zip(times, failures, risk):
        area += surv * (moment - previous)
        surv *= max(0., 1. - d / r)
        previous = moment
    if previous < HORIZON and surv > np.finfo(float).eps:
        raise ValueError('KM tail not identified through the registered horizon')
    return float(area)


def bootstrap_result(point, draws, data, **extra):
    good = np.asarray([v for v in draws if np.isfinite(v)], float)
    complete = len(good) == N_BOOTSTRAP
    # Incomplete draws remain diagnostic; no percentile interval is published.
    ci = np.quantile(good, [.025, .975]) if complete else [None, None]
    result = unavailable('' if complete else 'Some series resamples were not identified', data,
                         status='fit' if complete else 'bootstrap_incomplete')
    result.update(estimate=float(point), ci_low=ci[0], ci_high=ci[1], **extra)
    result['series_bootstrap']['successful_replicates'] = len(good)
    return result


def km_contrast(data):
    data = data.loc[data.remaining.between(0, LATE) & data.score_diff.isin([-1, 1])].copy()
    groups, inverse = np.unique(data.series_id.astype(str), return_inverse=True)
    trailing = data.score_diff.to_numpy() == -1
    def contrast(weights):
        return (km_rmst(data.latency[trailing], data.recovered[trailing], weights[trailing]) -
                km_rmst(data.latency[~trailing], data.recovered[~trailing], weights[~trailing]))
    try:
        if len(groups) < 3 or min(data.loc[data.score_diff.eq(s), 'series_id'].nunique() for s in (-1, 1)) < 3:
            raise ValueError('Insufficient series in L1 score cells')
        point = contrast(np.ones(len(data)))
        rng, draws = np.random.default_rng(SEED), []
        for _ in range(N_BOOTSTRAP):
            counts = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)))
            try:
                draws.append(contrast(counts[inverse]))
            except ValueError:
                draws.append(np.nan)
        return bootstrap_result(point, draws, data, units='seconds',
                                trailing_rmst=km_rmst(data.latency[trailing], data.recovered[trailing]),
                                leading_rmst=km_rmst(data.latency[~trailing], data.recovered[~trailing]))
    except ValueError as exc:
        return unavailable(str(exc), data)


def ols_contrast(data):
    data = data.loc[data.recovered & data.remaining.between(0, LATE) & data.score_diff.isin([-1, 1])].copy()
    try:
        if min(data.loc[data.score_diff.eq(s), 'series_id'].nunique() for s in (-1, 1)) < 3:
            raise ValueError('Insufficient uncensored series in L1 score cells')
        x = np.column_stack([np.ones(len(data)), data.score_diff.eq(-1).to_numpy(float)])
        fit = cluster_ols(x, data.latency, data.series_id)
        boot = bootstrap_ols(x, data.latency, data.series_id, 1, N_BOOTSTRAP, SEED)
        complete = boot['successful_replicates'] == N_BOOTSTRAP
        result = unavailable('', data, 'fit' if complete else 'bootstrap_incomplete')
        result.update(estimate=float(fit['beta'][1]), se=float(fit['se'][1]), p_value=float(fit['p'][1]),
                      ci_low=boot['ci_low'] if complete else None, ci_high=boot['ci_high'] if complete else None,
                      units='seconds', series_bootstrap=boot)
        return result
    except (ValueError, np.linalg.LinAlgError) as exc:
        return unavailable(str(exc), data)


def logit_design(data):
    # Fixed bins, no fitted quantiles: signed half, equal-width lateral thirds,
    # late/middle/early regulation clock bins. Raw boost is in replay units.
    x = [np.ones(len(data)), data.latency.to_numpy(float)]
    names = ['intercept', 'latency_seconds']
    for name, values, cuts in (
        ('ball_y_bin', data.ball_y.to_numpy(float), [0.]),
        ('ball_x_bin', data.ball_x.to_numpy(float), [-HALF_WIDTH/3, HALF_WIDTH/3]),
        ('clock_bin', data.remaining.to_numpy(float), [LATE, 180.])):
        codes = np.searchsorted(cuts, values, side='left')
        for level in range(1, len(cuts)+1):
            x.append((codes == level).astype(float))
            names.append(f'{name}={level}')
    x.append(data.opponent_boost.to_numpy(float) / 100.)
    names.append('opponent_mean_boost_per_100_raw_units')
    matrix = np.column_stack(x)
    # Drop only constants; aliased nonconstant adjustment columns fail closed.
    keep = [0, 1] + [j for j in range(2, matrix.shape[1]) if np.ptp(matrix[:, j]) > 0]
    omitted = [names[j] for j in range(matrix.shape[1]) if j not in keep]
    return matrix[:, keep], [names[j] for j in keep], omitted


def fit_logit(x, y, weights=None, start=None):
    """Unpenalized binomial MLE; reject singular, separated or nonconverged fits."""
    w = np.ones(len(y)) if weights is None else np.asarray(weights, float)
    active = w > 0
    if len(np.unique(y[active])) < 2 or np.linalg.matrix_rank(x[active]) < x.shape[1]:
        raise ValueError('Logit has one outcome class or singular adjustment design')
    beta = np.zeros(x.shape[1]) if start is None else np.array(start, copy=True)
    def objective(b):
        eta = x @ b
        return np.sum(w * (np.logaddexp(0., eta) - y * eta))
    for _ in range(80):
        p = expit(x @ beta)
        hessian = x.T @ ((w * p * (1 - p))[:, None] * x)
        if np.linalg.cond(hessian) > 1e12:
            raise ValueError('Logit information singular or separation suspected')
        score = x.T @ (w * (y - p))
        step = np.linalg.solve(hessian, score)
        old, scale = objective(beta), 1.
        while scale > 2.**-20 and objective(beta + scale * step) > old + 1e-10:
            scale *= .5
        beta = beta + scale * step
        if np.max(np.abs(beta)) > 50:
            raise ValueError('Logit separation suspected')
        if np.max(np.abs(step * scale)) < 1e-8 and np.max(np.abs(score)) < 1e-6:
            return beta, hessian
    raise ValueError('Logit did not converge')


def logit_contrast(data):
    data = data.loc[data.recovered & np.isfinite(data[['concede10', 'ball_x', 'ball_y', 'remaining', 'opponent_boost']]).all(axis=1)].copy()
    try:
        groups, inverse = np.unique(data.series_id.astype(str), return_inverse=True)
        if len(groups) < 3:
            raise ValueError('Insufficient independent series for L2')
        x, names, omitted = logit_design(data)
        y = data.concede10.to_numpy(float)
        beta, hessian = fit_logit(x, y)
        if len(y) <= x.shape[1]:
            raise ValueError('Insufficient observations for logit covariance')
        scores = np.zeros((len(groups), x.shape[1]))
        np.add.at(scores, inverse, x * (y - expit(x @ beta))[:, None])
        bread = np.linalg.inv(hessian)
        covariance = bread @ scores.T @ scores @ bread * len(groups)/(len(groups)-1) * (len(y)-1)/(len(y)-x.shape[1])
        se = np.sqrt(max(0., covariance[1, 1]))
        rng, draws = np.random.default_rng(SEED), []
        for _ in range(N_BOOTSTRAP):
            counts = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)))
            try:
                b, _ = fit_logit(x, y, counts[inverse], beta)
                draws.append(b[1])
            except (ValueError, np.linalg.LinAlgError):
                draws.append(np.nan)
        result = bootstrap_result(beta[1], draws, data, se=float(se),
                    p_value=float(2 * norm.sf(abs(beta[1] / se))) if se > 0 else None,
                    units='log odds per second', covariates=names, omitted_constant_covariates=omitted,
                    odds_ratio=float(np.exp(beta[1])), n_concessions=int(y.sum()))
        return result
    except (ValueError, np.linalg.LinAlgError) as exc:
        return unavailable(str(exc), data)


def direction_gate(contrasts, model):
    primary = contrasts[str(THRESHOLDS[0])][model]
    if primary['status'] != 'fit' or primary['ci_low'] is None:
        return False
    excludes = primary['ci_low'] > 0 or primary['ci_high'] < 0
    return bool(excludes and all(contrasts[str(r)][model]['status'] == 'fit'
        and np.sign(contrasts[str(r)][model]['estimate']) == np.sign(primary['estimate']) for r in THRESHOLDS))


def analyze(data, pilot=False):
    check_val(data)
    contrasts, feasibility = {}, {}
    for radius in THRESHOLDS:
        sub = data.loc[data.threshold.eq(radius)].copy() if len(data) else data.copy()
        feasibility[str(radius)] = dict(events=len(sub), series=int(sub.series_id.nunique()) if len(sub) else 0,
            recovered=int(sub.recovered.sum()) if len(sub) else 0,
            outcome_known=int(sub.concede10.notna().sum()) if len(sub) else 0,
            logit_complete_rows=int((sub.recovered & np.isfinite(sub[['concede10', 'ball_x', 'ball_y',
                                      'remaining', 'opponent_boost']]).all(axis=1)).sum()) if len(sub) else 0,
            audited_concessions=int(sub.concede10.eq(1).sum()) if len(sub) else 0,
            censor_reasons=sub.censor_reason.value_counts().to_dict() if len(sub) else {},
            late_score_cells={str(s): int((sub.remaining.le(LATE) & sub.score_diff.eq(s)).sum())
                              if len(sub) else 0 for s in (-1, 1)})
        if pilot or not len(sub):
            status = 'feasibility_only' if pilot else 'not_estimable'
            contrasts[str(radius)] = {name: unavailable('Pilot inference suppressed' if pilot else 'No eligible losses', sub, status)
                                      for name in MODELS}
        else:
            contrasts[str(radius)] = dict(zip(MODELS, (km_contrast(sub), ols_contrast(sub), logit_contrast(sub))))
    return dict(contrasts=contrasts, feasibility=feasibility,
                decisions={name: None if pilot else direction_gate(contrasts, model)
                           for name, model in (('L1', 'L1_km_rmst'), ('L2', 'L2_latency_logit'))},
                bootstrap=dict(replicates=N_BOOTSTRAP, seed=SEED, unit='whole series, all available games and focal views',
                               weighting='equal loss events; series resampling preserves event multiplicities'),
                pilot=pilot, pilot_inference_suppressed=pilot,
                definitions=dict(thresholds_uu=list(THRESHOLDS), horizon_seconds=HORIZON,
                    late_seconds=LATE, distance='planar Euclidean to own goal line centre',
                    L1='late trailing by one minus late leading by one; primary KM RMST, uncensored OLS companion',
                    L2='uncensored latency and known native outcome; adjusted log odds per second',
                    L2_window='any audited opponent goal in (loss, loss+horizon]; wall-clock seconds',
                    decision='primary interval excludes zero and both threshold sensitivity estimates have the same sign'),
                scope=dict(section='P5a only', season=VAL_SEASON, split='val', held_out_opened=False,
                           train_fitted_parameters=[]),
                limitations=['Associational estimates only.',
                    'Candidate contacts are a conservative last-touch proxy, not certified possession.',
                    'KM requires noninformative censoring; unobserved tails are not extrapolated.',
                    'L2 complete-case recovery selection and its overlapping outcome window can distort associations.',
                    'Unknown demolition duration and stale finite positions remain measurement limitations.',
                    'Series completeness is limited to available compact metadata.',
                    'Fixed geometry/bin choices operationalize details unspecified in the preregistration; no train fitting.',
                    'Raw model intervals; no additional multiplicity claim.'])


def run(compact, output, artifacts, pilot=False, data_root=DEFAULT_DATA_ROOT,
        state_map=Path('state_map_rlcs.json'), synthetic_events=None, scratch=None):
    started = time.perf_counter()
    compact, output, artifacts = map(guard_path, (compact, output, artifacts))
    scratch = guard_path(scratch) if scratch is not None else artifacts
    for dest in (output, artifacts, scratch):
        if dest.resolve() == compact.resolve() or compact.resolve() in dest.resolve().parents:
            raise ValueError('Outputs must not modify compact inputs')
    shards = inventory(compact)
    selected_ids = select_series(shards, pilot)
    selected = pd.concat([f.loc[f.series_id.isin(selected_ids)] for _, _, f in shards], ignore_index=True)
    manifest_path = guard_path(compact / 'extraction.json')
    manifest = json.loads(manifest_path.read_text())
    synthetic = manifest.get('synthetic_fixture') is True
    artifacts.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    selected.to_parquet(artifacts / 'selected_metadata.parquet', index=False)
    atomic_json(artifacts / 'selected_series.json', selected_ids)
    timing = dict(inventory_seconds=time.perf_counter() - started)
    tick = time.perf_counter()
    if synthetic_events is not None:
        if not synthetic:
            raise ValueError('Synthetic event override requires a labeled synthetic fixture')
        goals, replays = synthetic_events
        goals.to_parquet(artifacts / 'goal_events.parquet', index=False)
        replays.to_parquet(artifacts / 'replay_events.parquet', index=False)
    else:
        goals, replays = build_events(selected, artifacts, guard_path(data_root), guard_path(state_map))
    check_val(replays.assign(split='val'))
    if len(goals):
        check_val(goals.assign(split='val'))
    if set(replays.replay_id) != set(selected.replay_id) or replays.replay_id.duplicated().any():
        raise ValueError('Native event inventory does not match selected replays')
    by_replay = replays.set_index('replay_id').to_dict('index')
    timing['native_events_seconds'] = time.perf_counter() - tick
    tick = time.perf_counter()
    records, audit, sources, frames = [], Counter(), [], 0
    for metadata, shard, frame in shards:
        frame = frame.loc[frame.series_id.isin(selected_ids)]
        if frame.empty:
            continue
        with tempfile.TemporaryDirectory(prefix='p5-mmap-', dir=scratch) as tmp:
            arrays = mapped_shard(shard, Path(tmp))
            if frame.stop.max() > len(arrays['time']):
                raise ValueError('Slice exceeds compact arrays')
            for meta in frame.to_dict('records'):
                start, stop = int(meta['start']), int(meta['stop'])
                a = {key: val[start:stop] for key, val in arrays.items()}
                rows, counts = replay_losses(meta, a, goals.loc[goals.replay_id.eq(meta['replay_id'])], by_replay[meta['replay_id']])
                records.extend(rows)
                audit.update(counts)
                frames += stop - start
            del a, arrays
        sources.append(dict(metadata=str(metadata), arrays=str(shard),
                            metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
                            array_bytes=shard.stat().st_size, array_mtime_ns=shard.stat().st_mtime_ns))
    losses = pd.DataFrame.from_records(records)
    losses.to_parquet(artifacts / 'losses.parquet', index=False)
    timing['compact_and_losses_seconds'] = time.perf_counter() - tick
    tick = time.perf_counter()
    result = analyze(losses, pilot)
    timing['inference_seconds'] = time.perf_counter() - tick
    timing['total_seconds'] = time.perf_counter() - started
    measurement_passed = (selected.state_source.eq('explicit_state_map').all()
                          and replays.validated.eq(True).all())
    eligible = bool(not pilot and not synthetic and measurement_passed)
    result.update(data_kind='synthetic_self_test' if synthetic else 'validation_compact',
                  empirical_result=not synthetic, reporting_scope='feasibility_only' if pilot else ('synthetic_verification' if synthetic else 'associations'),
                  finding_eligible=eligible,
                  reported_findings={k: bool(eligible and v) for k, v in result['decisions'].items()},
                  measurement_gate=dict(passed=bool(measurement_passed)), audit=dict(audit), timing=timing,
                  provenance=dict(sources=sources, manifest=str(manifest_path), frames=frames,
                      perspectives=len(selected), replays=int(selected.replay_id.nunique()), series=len(selected_ids),
                      selected_series=str(artifacts / 'selected_series.json'), losses=str(artifacts / 'losses.parquet'),
                      module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      dependency_sha256={name: hashlib.sha256(Path(importlib.util.find_spec(
                          'tactics_code.' + Path(name).stem).origin).read_bytes()).hexdigest()
                          for name in ('common.py', 'events.py', 'data.py', 'stats.py')}))
    atomic_json(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path)
    parser.add_argument('--out', type=Path, default=Path('results/p5_latency.json'))
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts/p5-latency'))
    parser.add_argument('--scratch', type=Path, help='Optional local directory for temporary read-only mmap arrays')
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--state-map', type=Path, default=Path('state_map_rlcs.json'))
    parser.add_argument('--pilot', action='store_true', help='Registered whole-series feasibility sample; suppress inference')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        if args.pilot or args.compact:
            parser.error('--self-test cannot be combined with --pilot or --compact')
        path = Path(__file__).resolve().parents[1] / 'tests' / 'test_rotation_latency.py'
        spec = importlib.util.spec_from_file_location('p5_self_tests', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.OUTPUT_ROOT = args.artifacts.parent
        guard_path(module.OUTPUT_ROOT).mkdir(parents=True, exist_ok=True)
        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
        if not outcome.wasSuccessful():
            raise SystemExit(1)
        compact, events = module.write_fixture(args.artifacts / 'synthetic_compact')
        result = run(compact, args.out, args.artifacts, synthetic_events=events)
        if any(m['status'] != 'fit' for row in result['contrasts'].values() for m in row.values()):
            raise AssertionError('Synthetic pipeline did not fit all registered models')
        pilot_artifacts = args.artifacts.parent / 'p5-latency-pilot'
        pilot_compact, pilot_events = module.write_fixture(pilot_artifacts / 'synthetic_compact', PILOT_SERIES)
        pilot_result = run(pilot_compact, args.out.with_name(args.out.stem + '_pilot.json'),
                           pilot_artifacts, pilot=True, synthetic_events=pilot_events)
        if any(m['estimate'] is not None for row in pilot_result['contrasts'].values() for m in row.values()):
            raise AssertionError('Pilot inference was not suppressed')
    else:
        if args.compact is None:
            parser.error('--compact required')
        result = run(args.compact, args.out, args.artifacts, args.pilot, args.data_root, args.state_map,
                     scratch=args.scratch)
    print(json.dumps(dict(output=str(args.out), data_kind=result['data_kind'], timing=result['timing']), indent=2))
    return result


if __name__ == '__main__':
    main()
