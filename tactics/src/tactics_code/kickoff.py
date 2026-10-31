"""P6.2: validation-only kickoff associations, frozen training terciles.

Native states/events establish post-goal regulation starts. Compact geometry,
raw boost and candidate contacts supply explicitly labelled measurement proxies.
No network clients, scheduler submission, or test-season readers are used here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
import time
import zipfile
import shutil

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from .common import atomic_json, split_for_season
from .data import decode_replay_states, load_state_map
from .events import guard_path, native_index_for, _native_replays, build_replay_events
from .stats import cluster_ols

TRAIN = ('rlcs-21-22', 'rlcs-22-23', 'rlcs-2024')
VAL = 'rlcs-2025'
BOOTSTRAP = 2000
SEED = 42
WINDOW = 8.0
FOLLOWUP = 20.0
MAX_GAP = .2
COMPACT_TOL = .15
LATE = 60.0
EARLY = 180.0
PAD_RADIUS = 250.0
FULL_TOL = 1.0  # percent, permits replay quantization
MIN_JUMP = 15.0  # percent; exceeds a single small-pad increment
CONTROL_SECONDS = .2
CONTROL_RADIUS = 350.0
CONTROL_REL_SPEED = 1000.0
SPAWN_RADIUS = 200.0
SPAWNS = np.array([[-2048., -2560.], [2048., -2560.],
                   [-256., -3840.], [256., -3840.], [0., -4608.]])
SPAWN_NAMES = ('diagonal_left', 'diagonal_right', 'offset_left', 'offset_right', 'back_center')
CORNERS = np.array([[-3072., -4096.], [3072., -4096.],
                    [-3072., 4096.], [3072., 4096.]])
OUTCOMES = ('depth_at_T', 'max_depth_window', 'corner_pad_taken',
            'first_possession_focal', 'concede_20s')
TIME_BINS = ('late', 'early', 'opening')
RULES = dict(window_seconds=WINDOW, followup_seconds=FOLLOWUP, late_seconds=LATE,
             early_upper_seconds=EARLY, max_gap_seconds=MAX_GAP,
             compact_alignment_tolerance_seconds=COMPACT_TOL,
             pad_radius_uu=PAD_RADIUS, boost_full_tolerance_percent=FULL_TOL,
             boost_minimum_jump_percent=MIN_JUMP, spawn_radius_uu=SPAWN_RADIUS,
             control_seconds=CONTROL_SECONDS, control_radius_uu=CONTROL_RADIUS,
             control_relative_speed_uu_s=CONTROL_REL_SPEED,
             spawn_positions=SPAWNS.tolist(), corner_positions=CORNERS.tolist())
CAVEATS = [
    'All contrasts and tercile summaries are associations.',
    'The initial hit-latch transition marks the kickoff contest; it does not certify a two-car collision.',
    'Compact touch is the extractor candidate-contact proxy; missed contacts can lengthen T.',
    'First possession is a conservative controlled-contact proxy, not certified ball ownership.',
    'Control requires subsequent persistent proximity and relative-speed agreement; it is descriptive.',
    'Corner pickup is inferred from raw boost saturation and position, not a pad event log.',
    'Boost scale is explicit and frozen; raw replay units must match the supplied full-scale value.',
    'Countdown spawn ties use stable slot order and are counted; the actual touching kicker can differ.',
    'Compact sampling can miss pickups, contacts, or extrema between retained frames.',
    'Unknown demolition duration and stale finite tracks remain measurement limitations.',
    'Elapsed windows use parser current time, including non-live time for goal follow-up.',
    'Missing geometry, uncertain endpoints and censored outcomes remain null, never negative labels.',
    'Preregistration does not specify contact/control thresholds, exact time bins or the aggressiveness statistic; RULES documents these implementation choices.',
    'K1 uses maximum across the two fixed non-kickers at T; window maximum is a separate outcome.',
    'K2 uses the same endpoint depth for frozen terciles; its depth summaries are descriptive by construction.',
]


def checked_record(row, split):
    if split not in ('train', 'val'):
        raise ValueError('Only train/val records are permitted')
    expected = TRAIN if split == 'train' else (VAL,)
    if row.get('season') not in expected or row.get('split') != split:
        raise ValueError('Forbidden season/split before array access')
    if not isinstance(row.get('series_id'), str) or not row['series_id'].strip():
        raise ValueError('Known series ID required')


def metadata(root, split):
    """Explicit season allowlist; no traversal of the held-out directory."""
    root = guard_path(root)
    records = []
    for season in TRAIN if split == 'train' else (VAL,):
        for path in sorted(guard_path(root / season).glob('compact-*.parquet')):
            table = pd.read_parquet(guard_path(path))
            # Validate all metadata BEFORE opening the corresponding arrays.
            for row in table.to_dict('records'):
                checked_record(row, split)
                if row['season'] != season:
                    raise ValueError('Metadata season differs from directory')
                if row.get('state_decoding') != 'per_replay_decoded':
                    raise ValueError('Compact lacks per-replay decoded state provenance')
                row['_shard'] = str(guard_path(path.with_suffix('.npz')))
                row['_metadata'] = str(path)
                records.append(row)
    pairs = defaultdict(list)
    for row in records:
        pairs[str(row['replay_id'])].append(row)
    selected = []
    for rid, pair in sorted(pairs.items()):
        if len(pair) != 2 or {int(r['focal_team']) for r in pair} != {0, 1}:
            raise ValueError(f'Missing/duplicate focal perspective: {rid}')
        if len({(r['season'], r['series_id'], r['split']) for r in pair}) != 1:
            raise ValueError('Inconsistent focal perspectives')
        selected.append(next(r for r in pair if int(r['focal_team']) == 0))
    if not selected:
        raise ValueError(f'No {split} compact metadata')
    return selected


def kickoff_starts(frames, goals, summary):
    """Every goal-linked decoded countdown -> live return in regulation."""
    ordered = frames.sort_values('frame', kind='stable').reset_index(drop=True)
    decoded = decode_replay_states(ordered)
    if not summary['validated']:
        return []
    live, phase, ot = decoded['live'], decoded['phase'], decoded['overtime']
    t = ordered['current time'].to_numpy(float)
    f = ordered['frame'].to_numpy(float)
    remaining = ordered['seconds remaining'].to_numpy(float)
    hit = ordered['ball has been hit'].to_numpy(float)
    starts = np.flatnonzero(live[1:] & ~live[:-1]) + 1
    answer = []
    used = set()
    for i in starts:
        if phase[i-1] != 'kickoff' or ot[i] != 0 or remaining[i] <= 0:
            continue
        previous = [g for g in goals if g['frame'] < f[i] and g['regulation']]
        if not previous:
            continue  # opening kickoff and overtime restart are not post-goal units
        goal = previous[-1]
        if goal['goal_number'] in used:
            continue
        j = int(np.searchsorted(f, goal['frame']))
        if live[j:i].any():
            continue  # a later return without a new goal is not another kickoff
        used.add(goal['goal_number'])
        stop = i + 1
        while stop < len(live) and live[stop]:
            stop += 1
        onset = np.flatnonzero((hit[i:stop] > 0) &
                              (np.r_[hit[i-1], hit[i:stop-1]] == 0))
        score = sum(1 if g['scoring_team'] == 0 else -1 for g in goals if g['frame'] < f[i])
        answer.append(dict(kickoff_id=f"{summary['replay_id']}:{int(f[i])}",
                           start_time=float(t[i]), start_frame=int(f[i]),
                           countdown_time=float(t[i-1]),
                           remaining=float(remaining[i]), score_diff_blue=score,
                           contest_time=float(t[i+onset[0]]) if len(onset) else None,
                           live_end_time=float(t[stop]) if stop < len(t) else None))
    return answer


def concede_label(start, team, goals, summary):
    end = start + FOLLOWUP
    for g in goals:
        if g['scoring_team'] != team and start < g['time'] <= end:
            return 1.0, 'observed_concession'
    # A goal timing bracket straddling the horizon does not certify a negative.
    if any(g['scoring_team'] != team and g['last_live_time'] <= end < g['time']
           and g['time'] > start for g in goals):
        return np.nan, 'goal_bracket_crosses_horizon'
    observed_end = summary['observed_end_time']
    terminal = summary.get('terminal_time') if summary.get('terminal_verified') else None
    horizon = min(end, terminal) if terminal is not None and terminal >= start else end
    if observed_end < horizon:
        return np.nan, 'right_censored'
    gaps = zip(json.loads(summary['gap_start_times']), json.loads(summary['gap_end_times']))
    if any(a < horizon and b > start for a, b in gaps):
        return np.nan, 'native_gap_in_followup'
    return 0.0, 'complete_or_verified_terminal'


def spawn_assignment(players, ball, own, sign):
    positions = players[own, :3]
    if not np.isfinite(positions).all() or not np.isfinite(ball[:3]).all():
        return None
    distances = np.linalg.norm(positions - ball[None, :3], axis=1)
    kicker = own[int(np.argmin(distances))]
    tied = np.count_nonzero(np.isclose(distances, distances.min(), atol=1e-5, rtol=0)) > 1
    xy = players[kicker, :2] * sign
    distance = np.linalg.norm(SPAWNS - xy, axis=1)
    spawn = SPAWN_NAMES[int(distance.argmin())] if distance.min() <= SPAWN_RADIUS else None
    return kicker, [p for p in own if p != kicker], spawn, bool(tied), xy.tolist()


def controlled_touch(a, index, player):
    """Fixed descriptive confirmation rule; never present this as a true label."""
    t = np.asarray(a['time'])
    end = np.searchsorted(t, t[index] + CONTROL_SECONDS - 1e-7)
    if end >= len(t) or t[end] - t[index] > CONTROL_SECONDS + COMPACT_TOL:
        return False
    sl = slice(index, end+1)
    if not np.asarray(a['live'])[sl].all() or np.any(np.diff(t[sl]) > MAX_GAP + 1e-7):
        return False
    ball = np.asarray(a['ball'])[sl, :6]
    player_state = np.asarray(a['players'])[sl, player, :6]
    if not np.isfinite(ball).all() or not np.isfinite(player_state).all():
        return False
    distance = np.linalg.norm(player_state[:, :3] - ball[:, :3], axis=1)
    speed = np.linalg.norm(player_state[:, 3:6] - ball[:, 3:6], axis=1)
    return bool(np.all(distance <= CONTROL_RADIUS) and np.all(speed <= CONTROL_REL_SPEED))


def corner_pickup(a, indices, nonkickers, full_scale):
    players = np.asarray(a['players'])
    if players.shape[-1] <= 6 or full_scale is None:
        return np.nan, 'raw_boost_not_computable'
    if not len(indices) or indices[0] == 0:
        return np.nan, 'boost_baseline_missing'
    selected = np.r_[indices[0]-1, indices]
    b = players[selected][:, nonkickers, 6] * (100.0 / full_scale)
    xy = players[selected][:, nonkickers, :2]
    valid = np.isfinite(b) & (b >= 0) & (b <= 100.0 + FULL_TOL)
    near = np.min(np.linalg.norm(xy[1:, :, None, :] - CORNERS, axis=-1), axis=-1) <= PAD_RADIUS
    jumps = np.diff(b, axis=0)
    take = valid[1:] & valid[:-1] & near & (b[1:] >= 100.0 - FULL_TOL) & (jumps >= MIN_JUMP)
    dt = np.diff(np.asarray(a['time'])[selected])
    take &= (dt <= MAX_GAP + 1e-7)[:, None]
    if take.any():
        return 1.0, 'boost_jump_near_corner'
    if not valid.all() or not np.isfinite(xy).all() or np.any(dt > MAX_GAP + 1e-7):
        return np.nan, 'boost_or_position_incomplete'
    return 0.0, 'no_observed_corner_jump'


def replay_units(a, meta, starts, goals, summary, full_scale=255.0):
    checked_record(meta, meta['split'])
    t = np.asarray(a['time'], float)
    p, ball = np.asarray(a['players']), np.asarray(a['ball'])
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Compact clock must be finite and strictly increasing')
    if p.shape[:2] != (len(t), 6) or p.shape[-1] < 6 or ball.shape != (len(t), 6):
        raise ValueError('Unexpected compact geometry shape')
    touches = np.asarray(a.get('touch', np.full(len(t), -1)), int)
    rows = []
    for k in starts:
        s = k['start_time']
        baseline = int(np.searchsorted(t, s, side='left') - 1)
        begin = int(np.searchsorted(t, s, side='left'))
        base_ok = (baseline >= 0 and s - t[baseline] <= COMPACT_TOL + 1e-7
                   and not bool(a['live'][baseline]) and np.linalg.norm(ball[baseline, :2]) <= PAD_RADIUS)
        assignments = [spawn_assignment(p[baseline], ball[baseline], list(range(team*3, team*3+3)),
                                        1 if team == 0 else -1) if base_ok else None for team in (0, 1)]
        all_nonkickers = [player for assignment in assignments if assignment for player in assignment[1]]
        valid_assignments = all(x is not None and x[2] is not None for x in assignments)
        endpoint = s + WINDOW
        endpoint_reason = 'window_cap'
        contact_known = k['contest_time'] is not None and 'touch' in a and valid_assignments
        candidates = np.flatnonzero((t > (k['contest_time'] if k['contest_time'] is not None else np.inf)) &
                                     (t <= endpoint + 1e-7) & (t >= s) & np.isin(touches, all_nonkickers) &
                                     np.asarray(a['live'], bool))
        if k['live_end_time'] is not None:
            candidates = candidates[t[candidates] < k['live_end_time']]
        if len(candidates):
            endpoint = float(t[candidates[0]])
            endpoint_reason = 'first_non_kicker_candidate_touch'
        end = int(np.searchsorted(t, endpoint + 1e-7, side='right') - 1)
        indices = np.arange(begin, end+1)
        complete = (len(indices) > 0 and end < len(t) and t[begin] - s <= COMPACT_TOL + 1e-7
                    and endpoint - t[end] <= COMPACT_TOL + 1e-7
                    and np.asarray(a['live'])[indices].all()
                    and np.all(np.diff(t[np.r_[baseline, indices]]) <= MAX_GAP + 1e-7)
                    and (k['live_end_time'] is None or endpoint < k['live_end_time']))
        if not contact_known:
            window_reason = 'kickoff_contest_or_touch_unavailable'
        elif not complete:
            window_reason = 'window_truncated_or_gap'
        else:
            window_reason = 'complete'
        valid_window = complete and contact_known
        owner = None
        if valid_window:
            for i in candidates[t[candidates] <= endpoint + 1e-7]:
                if controlled_touch(a, i, touches[i]):
                    owner = int(touches[i] >= 3)
                    break
        for team in (0, 1):
            sign = 1 if team == 0 else -1
            assignment = assignments[team]
            score = k['score_diff_blue'] * sign
            row = dict(replay_id=str(meta['replay_id']), series_id=meta['series_id'],
                       season=meta['season'], split=meta['split'], focal_team=team, **k,
                       score_diff=score, time_bin=('late' if k['remaining'] <= LATE else
                                                  'early' if k['remaining'] <= EARLY else 'opening'),
                       T=endpoint-s, endpoint_time=endpoint, endpoint_reason=endpoint_reason,
                       window_status=window_reason, kicker=None, spawn=None, spawn_tie=None,
                       kicker_spawn_x=None, kicker_spawn_y=None, nonkickers=None,
                       depth_at_T=np.nan, max_depth_window=np.nan, corner_pad_taken=np.nan,
                       boost_status='window_unavailable', first_possession_team=owner,
                       first_possession_focal=float(owner == team) if owner is not None else np.nan,
                       possession_status='controlled_contact_proxy' if owner is not None else 'not_observed_or_unavailable')
            if assignment:
                kicker, nonkickers, spawn, tied, xy = assignment
                row.update(kicker=kicker, nonkickers=json.dumps(nonkickers), spawn=spawn, spawn_tie=tied,
                           kicker_spawn_x=xy[0], kicker_spawn_y=xy[1])
                if valid_window:
                    positions = p[indices][:, nonkickers, :3]
                    present = np.isfinite(positions).all()
                    if p.shape[-1] > 7:
                        present = present and not np.any(p[indices][:, nonkickers, 7] == 1)
                    if present:
                        depth = positions[:, :, 1] * sign
                        row.update(depth_at_T=float(depth[-1].max()), max_depth_window=float(depth.max()))
                    row['corner_pad_taken'], row['boost_status'] = corner_pickup(a, indices, nonkickers, full_scale)
            row['concede_20s'], row['concede_status'] = concede_label(s, team, goals, summary)
            rows.append(row)
    return rows


def freeze_thresholds(train, full_scale=255.0):
    """Unweighted empirical unit terciles on TRAIN; never fit on validation."""
    for row in train.to_dict('records'):
        checked_record(row, 'train')
    values = train['depth_at_T'].dropna().to_numpy(float) if 'depth_at_T' in train else np.array([])
    values = values[np.isfinite(values)]
    edges = np.quantile(values, [1/3, 2/3]).tolist() if len(values) else None
    valid = edges is not None and edges[0] < edges[1]
    return dict(schema='p6-kickoff-thresholds-v1', fit_split='train', fit_seasons=sorted(train['season'].unique())
                if len(train) else [], n_train_units=int(len(values)),
                n_train_series=int(train['series_id'].nunique()) if len(train) else 0,
                source_digest=hashlib.sha256(train.to_json(orient='records').encode()).hexdigest(),
                statistic='max fixed non-kicker forward y at T', weighting='each kickoff-team unit equally',
                tercile_edges=edges if valid else None, status='frozen' if valid else 'unavailable_training_support',
                rules=RULES, boost_full_scale=full_scale)


def validate_thresholds(frozen):
    if (frozen.get('schema') != 'p6-kickoff-thresholds-v1' or frozen.get('fit_split') != 'train'
            or not set(frozen.get('fit_seasons', [])) <= set(TRAIN) or frozen.get('rules') != RULES):
        raise ValueError('Untrusted or incompatible training threshold artifact')
    edges = frozen.get('tercile_edges')
    if edges is not None and (len(edges) != 2 or not np.isfinite(edges).all() or edges[0] >= edges[1]):
        raise ValueError('Invalid training terciles')
    if edges is not None and (not frozen.get('fit_seasons') or frozen.get('n_train_units', 0) < 1
                              or frozen.get('n_train_series', 0) < 1):
        raise ValueError('Frozen terciles require documented training support')


def nuisance_matrix(df, fields):
    arrays, names = [np.ones(len(df))], ['intercept']
    for field in fields:
        levels = sorted(df[field].astype(str).unique())
        for level in levels[1:]:
            arrays.append(df[field].astype(str).eq(level).to_numpy(float))
            names.append(f'{field}={level}')
    return np.column_stack(arrays), names


def infer(x, y, series, contrasts, repeats=BOOTSTRAP, seed=SEED):
    """CR1 plus actual whole-series OLS refits via cluster sufficient statistics."""
    result = {name: dict(estimate=None, cr1_se=None, cr1_ci=None, bootstrap_ci=None,
                         bootstrap_successful=0, bootstrap_requested=repeats,
                         status='not_estimable') for name in contrasts}
    try:
        fit = cluster_ols(x, y, series)
    except (ValueError, np.linalg.LinAlgError) as exc:
        for value in result.values():
            value['reason'] = str(exc)
        return result
    labels, inverse = np.unique(np.asarray(series, str), return_inverse=True)
    n, p = x.shape
    beta = fit['beta']
    bread = np.linalg.inv(x.T @ x)
    score = np.zeros((len(labels), p))
    np.add.at(score, inverse, x * (y-x @ beta)[:, None])
    cov = bread @ score.T @ score @ bread * len(labels)/(len(labels)-1) * (n-1)/(n-p)
    xx = np.array([x[inverse == g].T @ x[inverse == g] for g in range(len(labels))])
    xy = np.array([x[inverse == g].T @ y[inverse == g] for g in range(len(labels))])
    c = np.array(list(contrasts.values()))
    draws = []
    rng = np.random.default_rng(seed)
    for _ in range(repeats):
        count = rng.multinomial(len(labels), np.full(len(labels), 1/len(labels)))
        lhs = np.einsum('g,gij->ij', count, xx)
        if np.linalg.matrix_rank(lhs) == p:
            draws.append(c @ np.linalg.solve(lhs, count @ xy))
    for i, name in enumerate(contrasts):
        se = float(np.sqrt(max(0., c[i] @ cov @ c[i])))
        estimate = float(c[i] @ beta)
        radius = float(student_t.ppf(.975, len(labels)-1)) * se
        ci = np.quantile(np.array(draws)[:, i], [.025, .975]).tolist() if draws else None
        result[name].update(estimate=estimate, cr1_se=se, cr1_ci=[estimate-radius, estimate+radius],
                            bootstrap_ci=ci, bootstrap_successful=len(draws),
                            status='estimated' if len(draws) == repeats else 'incomplete_bootstrap',
                            n_units=n, n_series=len(labels))
    return result


def empty_estimate(reason):
    return dict(status='not_estimable', reason=reason, estimate=None, cr1_se=None,
                cr1_ci=None, bootstrap_ci=None, bootstrap_requested=BOOTSTRAP,
                bootstrap_successful=0, n_units=0, n_series=0)


def primary(df):
    results = {}
    for label in ('pooled',) + TIME_BINS:
        part = df if label == 'pooled' else df[df['time_bin'] == label]
        part = part[part['score_diff'].isin([-1, 1])].dropna(subset=['depth_at_T', 'spawn', 'series_id', 'time_bin'])
        if set(part['score_diff']) != {-1, 1}:
            result = empty_estimate('both exact score arms required')
        else:
            x, names = nuisance_matrix(part, ['spawn', 'time_bin'] if label == 'pooled' else ['spawn'])
            x = np.column_stack([x, part['score_diff'].eq(-1).to_numpy(float)])
            contrast = np.eye(x.shape[1])[-1]
            result = infer(x, part['depth_at_T'].to_numpy(float), part['series_id'],
                           {'trailing_minus_leading': contrast})['trailing_minus_leading']
            result['design_columns'] = names + ['trailing_by_one']
        result['arm_counts'] = {str(arm): int(part['score_diff'].eq(arm).sum()) for arm in (-1, 1)}
        ci = result['bootstrap_ci']
        result['finding'] = bool(result['status'] == 'estimated' and ci is not None and (ci[0] > 0 or ci[1] < 0))
        results[label] = result
    return results


def secondary(df, frozen):
    edges = frozen.get('tercile_edges')
    frame = df.copy()
    if edges is not None:
        frame['tercile'] = np.searchsorted(edges, frame['depth_at_T'].fillna(np.inf), side='left')
    else:
        frame['tercile'] = -1
    result = {}
    for outcome in OUTCOMES:
        valid = frame.dropna(subset=['depth_at_T', outcome, 'spawn', 'score_diff', 'time_bin', 'series_id'])
        descriptive = {}
        for group, name in enumerate(('low', 'middle', 'high')):
            part = valid[valid['tercile'] == group]
            descriptive[name] = dict(n_units=len(part), n_series=int(part['series_id'].nunique()),
                                     mean=float(part[outcome].mean()) if len(part) else None)
        names = ('low', 'middle', 'high', 'middle_minus_low', 'high_minus_low')
        block = dict(outcome=outcome, raw_by_tercile=descriptive,
                     n_missing=int(frame[outcome].isna().sum()), adjusted={})
        if edges is None or set(valid['tercile']) != {0, 1, 2}:
            block['adjusted'] = {name: empty_estimate('frozen terciles unavailable or all terciles not supported') for name in names}
        else:
            x, columns = nuisance_matrix(valid, ['spawn', 'score_diff', 'time_bin'])
            x = np.column_stack([x, valid['tercile'].eq(1).to_numpy(float), valid['tercile'].eq(2).to_numpy(float)])
            vectors = {}
            for group, name in enumerate(names[:3]):
                c = x.mean(axis=0)
                c[-2:] = [float(group == 1), float(group == 2)]
                vectors[name] = c
            vectors['middle_minus_low'] = vectors['middle'] - vectors['low']
            vectors['high_minus_low'] = vectors['high'] - vectors['low']
            block['adjusted'] = infer(x, valid[outcome].to_numpy(float), valid['series_id'], vectors)
            block['design_columns'] = columns + ['middle_tercile', 'high_tercile']
        result[outcome] = block
    return result


def analyze(units, frozen):
    validate_thresholds(frozen)
    for row in units.to_dict('records'):
        checked_record(row, 'val')
    required = set(OUTCOMES) | {'score_diff', 'time_bin', 'spawn', 'series_id', 'depth_at_T'}
    units = units.copy()
    for column in required - set(units):
        units[column] = pd.Series(dtype=float if column in OUTCOMES else object)
    summary = {}
    for outcome in OUTCOMES:
        values = units[outcome].dropna()
        summary[outcome] = dict(n_observed=len(values), n_null=int(units[outcome].isna().sum()),
                                mean=float(values.mean()) if len(values) else None)
    return dict(task='P6.2', status='estimated' if len(units) else 'no_eligible_units',
                interpretation='associational', analysis_split='val', analysis_season=VAL,
                n_units=len(units), n_series=int(units['series_id'].nunique()),
                bootstrap=dict(unit='whole series, both teams and all included replays retained',
                               repeats=BOOTSTRAP, seed=SEED, fixed_train_thresholds=True),
                thresholds=frozen, rules=RULES, outcomes=summary,
                first_possession_team_counts=units['first_possession_team'].fillna('unobserved').value_counts().to_dict()
                    if 'first_possession_team' in units else {},
                primary_contrast='K1.pooled; time-bin contrasts are also reported without selection',
                endpoint_convention='Last compact state at or before T, within the frozen alignment tolerance',
                K1=primary(units), K2=secondary(units, frozen), caveats=CAVEATS,
                test_season_opened=False)


def collect(records, data_root, state_map, output, full_scale):
    """Native selected-only event reads, then disk-backed compact arrays by shard."""
    started = time.perf_counter()
    native = native_index_for(records, guard_path(data_root))
    lookup = {str(row['replay_id']): row for row in native}
    by_native = defaultdict(set)
    for row in native:
        by_native[row['_frame_path']].add(str(row['replay_id']))
    contexts, audits, all_goals = {}, [], []
    native_frames = 0
    for path, ids in sorted(by_native.items()):
        for rid, frames in _native_replays(path, ids):
            goals, summary = build_replay_events(frames, lookup[rid], state_map)
            starts = kickoff_starts(frames, goals, summary)
            contexts[rid] = (starts, goals, summary)
            audits.append(summary)
            all_goals.extend(goals)
            native_frames += len(frames)
    event_seconds = time.perf_counter() - started
    shard_rows = defaultdict(list)
    for row in records:
        shard_rows[row['_shard']].append(row)
    units, sources = [], set()
    compact_started = time.perf_counter()
    for shard, rows in sorted(shard_rows.items()):
        guard_path(shard)
        with tempfile.TemporaryDirectory(prefix='compact-', dir=output) as temp:
            arrays = {}
            with zipfile.ZipFile(shard) as archive:
                for key in ('ball', 'players', 'time', 'frame', 'live', 'touch'):
                    name = key + '.npy'
                    if name not in archive.namelist():
                        if key == 'touch':
                            continue
                        raise ValueError(f'Missing compact array {key}')
                    target = Path(temp) / name
                    with archive.open(name) as source, target.open('wb') as dest:
                        shutil.copyfileobj(source, dest)
                    arrays[key] = np.load(target, mmap_mode='r', allow_pickle=False)
            for row in rows:
                checked_record(row, row['split'])
                begin, end = int(row['start']), int(row['stop'])
                if not (0 <= begin < end <= len(arrays['time'])):
                    raise ValueError('Invalid compact slice')
                a = {key: value[begin:end] for key, value in arrays.items()}
                rid = str(row['replay_id'])
                starts, goals, summary = contexts[rid]
                units.extend(replay_units(a, row, starts, goals, summary, full_scale))
                sources.update((shard, row['_metadata'], summary['native_path']))
            del arrays
    table = pd.DataFrame(units)
    pd.DataFrame(audits).to_parquet(output / 'replay_events.parquet', index=False)
    pd.DataFrame(all_goals).to_parquet(output / 'goal_events.parquet', index=False)
    table.to_parquet(output / 'kickoff_units.parquet', index=False)
    return table, dict(n_replays=len(records), n_native_frames=native_frames,
                       n_validated_replays=sum(bool(r['validated']) for r in audits),
                       event_seconds=event_seconds, compact_seconds=time.perf_counter()-compact_started,
                       source_files=sorted(sources), replay_failure_counts=dict(Counter(
                           r['failure_reason'] for r in audits if not r['validated'])))


def select_series(records, cap):
    if cap is None:
        return records
    if cap < 1:
        raise ValueError('Pilot series cap must be positive')
    series = sorted({r['series_id'] for r in records},
                    key=lambda s: hashlib.sha256(f'{SEED}:{s}'.encode()).hexdigest())[:cap]
    return [r for r in records if r['series_id'] in series]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--state-map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Writable analysis root')
    parser.add_argument('--thresholds', type=Path, help='Previously frozen TRAIN artifact; skips all train reads')
    parser.add_argument('--boost-full-scale', type=float, default=255.0,
                        help='Raw replay value representing full boost; frozen before validation')
    parser.add_argument('--pilot-series', type=int, help='Whole-series feasibility cap per split; not a full result')
    args = parser.parse_args(argv)
    if not np.isfinite(args.boost_full_scale) or args.boost_full_scale <= 0:
        parser.error('boost-full-scale must be positive and finite')
    root = args.output.resolve()
    for source in (args.compact, args.data_root):
        source = guard_path(source).resolve()
        if root == source or source in root.parents or root in source.parents:
            raise ValueError('Output and input trees must be disjoint')
    root.mkdir(parents=True, exist_ok=True)
    artifacts = root / 'artifacts' / 'p6_kickoff'
    artifacts.mkdir(parents=True, exist_ok=True)
    state_map_path = guard_path(args.state_map)
    state_map = load_state_map(state_map_path)
    if state_map.get('state_decoding') != 'per_replay_decoded':
        raise ValueError('Per-replay decoded state map required')
    timing, train_ids = {}, set()
    if args.thresholds:
        frozen = json.loads(guard_path(args.thresholds).read_text())
        validate_thresholds(frozen)
        if frozen['boost_full_scale'] != args.boost_full_scale:
            raise ValueError('Boost scale differs from frozen training artifact')
        train_ids = set(frozen.get('train_series_ids', []))
    else:
        train_records = metadata(args.compact, 'train')
        train_ids = {r['series_id'] for r in train_records}
        selected = select_series(train_records, args.pilot_series)
        directory = artifacts / 'train'
        directory.mkdir(exist_ok=True)
        train, timing['train'] = collect(selected, args.data_root, state_map, directory, args.boost_full_scale)
        frozen = freeze_thresholds(train, args.boost_full_scale)
        frozen.update(train_series_ids=sorted(train_ids), pilot=bool(args.pilot_series),
                      source_files=timing['train']['source_files'])
        timing['train']['available_replays'] = len(train_records)
    # Persist TRAIN artifact before any validation metadata or array access.
    atomic_json(artifacts / 'train_thresholds.json', frozen)
    val_records = metadata(args.compact, 'val')
    if train_ids & {r['series_id'] for r in val_records}:
        raise ValueError('A series crosses train/validation')
    selected = select_series(val_records, args.pilot_series)
    directory = artifacts / 'val'
    directory.mkdir(exist_ok=True)
    val, timing['val'] = collect(selected, args.data_root, state_map, directory, args.boost_full_scale)
    timing['val']['available_replays'] = len(val_records)
    started = time.perf_counter()
    report = analyze(val, frozen)
    timing['inference_seconds'] = time.perf_counter()-started
    report.update(status='feasibility_only' if args.pilot_series or frozen.get('pilot') else report['status'],
                  timing=timing, extraction_status_counts={column: val[column].value_counts(dropna=False).to_dict()
                    for column in ('window_status', 'boost_status', 'possession_status', 'concede_status', 'spawn_tie') if column in val},
                  sources=dict(preregistration='docs/P6_reviewer_prereg.md#P6.2',
                               state_map=str(state_map_path), state_map_sha256=hashlib.sha256(state_map_path.read_bytes()).hexdigest(),
                               module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
                  timing_estimate=dict(replay_processing_seconds=sum(
                      (v['event_seconds']+v['compact_seconds'])*v['available_replays']/v['n_replays']
                      for v in timing.values() if isinstance(v, dict)),
                      inference_seconds=timing['inference_seconds'],
                      caveat='Pilot linear replay extrapolation; inference and storage throughput must be checked on target CPU.'))
    atomic_json(root / 'results' / 'p6_kickoff.json', report)
    print(json.dumps(dict(result=str(root / 'results' / 'p6_kickoff.json'), status=report['status'], timing=timing)))


if __name__ == '__main__':
    main()
