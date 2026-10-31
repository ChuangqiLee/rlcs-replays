"""Development-only defensive-depth risk contrasts and DR diagnostics.

Default C2 state design: because all six current player coordinates are required controls, depth-tercile
assignment is deterministic given X. We compute the requested numerical AIPW
contrasts for audit, but always fail the causal positivity gate for state. Their labels,
JSON and dose curves describe exploratory state-outcome associations. A fitted
propensity in (0,1) cannot repair this structural identification failure.

C3 initiation is a separate, observational one-second displacement design with
full baseline state controls and frozen defender identity. Empirical overlap is
assessable, not guaranteed. Early-goal exclusion selects one-second survivors;
causal interpretation requires no unmeasured confounding and noninformative
landmark selection, in addition to consistency and overlap.

No 2026 directory, metadata, NPZ array, or native replay is opened. Outcomes use
native decoded goal events and may cross live-segment boundaries. Both focal
views remain in the same series for folds, weights and bootstrap resampling.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss
from joblib import Parallel, delayed, parallel_config
from threadpoolctl import threadpool_limits

from .common import atomic_json, now
from .data import DEFAULT_DATA_ROOT
from .events import build_events, guard_path
from .pressure import last_man_arrays
from .screen import (ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, REQUIRED,
                     metadata_inventory, read_slice, unpack_shard)

MEDIUM = Path('artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact')
SMALL = Path('artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact')
HORIZONS = (5, 10, 15)
BALL_EDGES = np.array([-np.inf, -2560., 0., 2560., np.inf])
OUTCOMES = ('for', 'against')
BALL_FEATURES = [f'ball_{x}' for x in ('x', 'y', 'z', 'vx', 'vy', 'vz')]
PLAYER_FEATURES = [f'{team}{j}_{x}' for team in ('own', 'opp') for j in range(3)
                   for x in ('x', 'y', 'z', 'vx', 'vy', 'vz', 'boost')]
NUMERIC_FEATURES = BALL_FEATURES + PLAYER_FEATURES + ['remaining', 'score_diff']
LABELS = ('y5', 'y10', 'y15', 'ypast10')
INITIATION_WINDOW = 1.
DEFAULT_DELTA = 500.
DEFAULT_DELTA_SENSITIVITIES = (300., 800.)
OVERLAP_GATES = {'minimum_series': 50, 'minimum_arm_series': 20,
                 'minimum_unique_goals': 50, 'minimum_anchor_ess': 100,
                 'minimum_series_ess': 20, 'maximum_extreme_mass': .1,
                 'maximum_trim_fraction': .2, 'maximum_smd': .1}


def parallel_tasks(function, tasks, workers=1, inner_threads=1):
    if workers == 1:
        with threadpool_limits(limits=inner_threads):
            return [function(*args) for args in tasks]
    with parallel_config(backend='loky', inner_max_num_threads=inner_threads):
        return Parallel(n_jobs=min(workers, len(tasks)))(delayed(function)(*args) for args in tasks)



def stable_hash(value):
    return int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:8], 'little')


def select_pairs(pairs, max_replays=None, replay_ids=None, seed=42):
    """Outcome-blind deterministic season round robin for bounded smoke only."""
    if replay_ids is not None:
        text = guard_path(replay_ids).read_text()
        try:
            wanted = set(json.loads(text))
        except json.JSONDecodeError:
            wanted = set(text.splitlines())
        pairs = [p for p in pairs if p[0]['replay_id'] in wanted]
        if {p[0]['replay_id'] for p in pairs} != wanted:
            raise ValueError('Requested replay IDs are absent from allowed development metadata')
    if max_replays is None:
        return pairs
    if max_replays < 1:
        raise ValueError('--max-replays must be positive')
    by_season = {s: [] for s in ALLOWED_SEASONS}
    for pair in pairs:
        by_season[pair[0]['season']].append(pair)
    for rows in by_season.values():
        rows.sort(key=lambda p: stable_hash(f'{seed}:{p[0]["replay_id"]}'))
    selected = []
    while len(selected) < max_replays and any(by_season.values()):
        for season in ALLOWED_SEASONS:
            if by_season[season] and len(selected) < max_replays:
                selected.append(by_season[season].pop(0))
    return selected


def fixed_anchor_indices(times, series_id, seed=42, spacing=1.):
    """State at or immediately before an outcome-independent absolute grid."""
    phase = (stable_hash(f'{seed}:{series_id}:anchor') % 1000000) / 1000000 * spacing
    first = math.ceil((float(times[0])-phase)/spacing) * spacing + phase
    grid = np.arange(first, float(times[-1])+1e-9, spacing)
    indices = np.searchsorted(times, grid, side='right') - 1
    good = (indices >= 0) & ((grid-times[np.maximum(indices, 0)]) <= .150001)
    return indices[good], grid[good]


def valid_baseline(a):
    """Past-only six-track availability screen; no future persistence test."""
    p, b, t = a['players'], a['ball'], a['time']
    valid = (a['live'].astype(bool) & (a['segment'] >= 0) &
             (a['overtime'] == 0) & np.isfinite(p[:, :, :7]).all(axis=(1, 2)) &
             np.isfinite(b[:, :6]).all(axis=1) & np.isfinite(t) &
             np.isfinite(a['remaining']) & np.isfinite(a['score_diff']) &
             ~np.any(p[:, :, 7] == 1, axis=1))
    # Raw demolition actor IDs are not a persistent absence indicator. Do not
    # invent their semantics. Flag stale coordinates using only elapsed past.
    stationary_since = np.zeros((len(t), 6), dtype=float)
    if len(t):
        stationary_since[0] = t[0]
    for i in range(1, len(t)):
        continuous = (0 < t[i]-t[i-1] <= .16 and a['segment'][i] == a['segment'][i-1])
        same = np.all(p[i, :, :3] == p[i-1, :, :3], axis=1) & continuous
        stationary_since[i] = np.where(same, stationary_since[i-1], t[i])
        valid[i] &= not np.any(t[i]-stationary_since[i] >= 1.)
        if continuous:
            valid[i] &= (np.linalg.norm(p[i, :, :3]-p[i-1, :, :3], axis=1).max() <= 500)
    return valid


def event_labels(anchor_times, focal_team, goals, replay, followup_delay=0., include_window_goals=False):
    """Competing first-goal labels; unknown truncated tails remain missing."""
    g = goals.sort_values('time')
    gt = g['time'].to_numpy(float)
    teams = g['scoring_team'].to_numpy(int)
    frames = g['frame'].to_numpy(int)
    n = len(anchor_times)
    after = np.searchsorted(gt, anchor_times if include_window_goals else anchor_times+followup_delay, side='right')
    observed_end = float(replay['observed_end_time'])
    observed_start = replay.get('observed_start_time', np.nan)
    terminal_verified = bool(replay.get('terminal_verified', False))
    terminal = replay.get('terminal_time')
    terminal = float(terminal) if pd.notna(terminal) else np.inf
    # Regulation is baseline eligibility, not a future censoring rule. Follow
    # through clock zero/OT if necessary; only certified game end is absorbing.
    stop = terminal if terminal_verified else np.inf
    gap_starts = np.asarray(json.loads(replay.get('gap_start_times', '[]')), float)
    gap_ends = np.asarray(json.loads(replay.get('gap_end_times', '[]')), float)
    out = {}
    for horizon in HORIZONS:
        deadline = np.minimum(anchor_times+followup_delay+horizon, stop)
        known = (deadline <= observed_end + 1e-7)
        yy = np.where(known, 0., np.nan)
        goal_id = np.full(n, '', dtype=object)
        for i, j in enumerate(after):
            if j < len(gt) and gt[j] <= deadline[i] + 1e-7:
                yy[i] = 1 if teams[j] == focal_team else 2
                goal_id[i] = f'{replay["replay_id"]}:{frames[j]}'
            required_end = gt[j] if goal_id[i] else deadline[i]
            if np.any((gap_starts < required_end) & (gap_ends > anchor_times[i])):
                yy[i], goal_id[i] = np.nan, ''
        out[f'y{horizon}'] = yy
        out[f'goal_id{horizon}'] = goal_id
    # Latest preceding event in (t-10,t]; a diagnostic, not a valid causal test
    # when baseline behavior responds to the past. Degenerate support is explicit.
    before = np.searchsorted(gt, anchor_times, side='right') - 1
    past = np.zeros(n, dtype=float)
    if pd.notna(observed_start):
        past[anchor_times-10 < float(observed_start)] = np.nan
    else:
        past[:] = np.nan
    for i, j in enumerate(before):
        if j >= 0 and gt[j] > anchor_times[i]-10 and np.isfinite(past[i]):
            past[i] = 1 if teams[j] == focal_team else 2
    for i, anchor in enumerate(anchor_times):
        if np.any((gap_starts < anchor) & (gap_ends > anchor-10)):
            past[i] = np.nan
    out['ypast10'] = past
    return out


def initiation_measurement(a, indices, goals, replay, window=INITIATION_WINDOW):
    """Fixed-slot displacement; endpoint interpolation never uses reset frames.

    Baseline eligibility is already fixed. Future missingness is an unknown
    treatment measurement, not a new eligibility rule. Early-goal sensitivity
    truncates at the final pre-goal live frame and declares the altered exposure.
    """
    times = np.asarray(a['time'], float)
    players = np.asarray(a['players'])
    identities = last_man_arrays(a)['last_man_index'][indices]
    sorted_goals = goals.sort_values('time')
    gt = sorted_goals['time'].to_numpy(float)
    gaps0 = np.asarray(json.loads(replay.get('gap_start_times', '[]')), float)
    gaps1 = np.asarray(json.loads(replay.get('gap_end_times', '[]')), float)
    displacement, sensitivity, early, durations = [], [], [], []
    for i, identity in zip(indices, identities):
        start, end = times[i], times[i]+window
        first = np.searchsorted(gt, start, side='right')
        hit = first < len(gt) and gt[first] <= end+1e-7
        early.append(hit)
        def measure(stop):
            if stop <= start or stop > times[-1]+1e-7:
                return np.nan
            right = int(np.searchsorted(times, stop, side='left'))
            right = min(right, len(times)-1)
            left = right if abs(times[right]-stop) < 1e-6 else right-1
            if left < i or times[right]-times[left] > .160001:
                return np.nan
            span = slice(i, right+1)
            if (not np.all(a['segment'][span] == a['segment'][i]) or
                    not np.all(a['live'][span]) or np.any(np.diff(times[span]) > .160001) or
                    np.any((gaps0 < stop) & (gaps1 > start)) or
                    np.any(players[span, identity, 7] == 1) or
                    not np.isfinite(players[span, identity, 1]).all()):
                return np.nan
            # Only the frozen defender's position is needed after baseline.
            # No future teammate state, velocity, boost or re-ranking is used.
            yy = players[[left, right], identity, 1]
            if not np.isfinite(yy).all() or np.any(players[[left, right], identity, 7] == 1):
                return np.nan
            endpoint = yy[0] if left == right else np.interp(stop, times[[left, right]], yy)
            return float(endpoint-players[i, identity, 1])
        displacement.append(np.nan if hit else measure(end))
        if hit:
            # Compact frame strictly before native goal, in the same live segment.
            before = np.flatnonzero((times > start) & (times < gt[first]) &
                                    (a['segment'] == a['segment'][i]) & a['live'].astype(bool))
            stop = times[before[-1]] if len(before) else start
            sensitivity.append(measure(stop))
            durations.append(stop-start)
        else:
            sensitivity.append(displacement[-1])
            durations.append(window)
    return {'displacement_1s': displacement, 'displacement_including_early': sensitivity,
            'early_goal': early, 'exposure_observed_seconds': durations}


def anchors_for_replay(meta, a, goals, replay, seed, spacing=1., design='state'):
    if meta['season'] not in ALLOWED_SEASONS or meta['split'] not in ('train', 'val'):
        raise ValueError('NEVER read 2026/test')
    if not bool(replay['validated']):
        return pd.DataFrame(), {'invalid_event_replay': 1}
    t = np.asarray(a['time'], float)
    if len(t) < 2 or not np.all(np.diff(t) > 0):
        return pd.DataFrame(), {'invalid_time_replay': 1}
    ii, tt = fixed_anchor_indices(t, meta['series_id'], seed, spacing)
    initial = len(ii)
    valid = valid_baseline(a)
    valid &= (a['remaining'] >= 10) & (a['remaining'] <= 180)
    valid &= np.isin(a['score_diff'], [-1, 1] if design == 'state' else [-1, 0, 1])
    depths = last_man_arrays(a)
    valid &= depths['last_man_valid']
    valid &= (t >= float(replay['observed_start_time'])) & (t <= float(replay['observed_end_time']))
    native_score = np.zeros(len(ii), dtype=int)
    for event in goals.itertuples():
        native_score += (t[ii] > event.time) * (1 if int(event.scoring_team) == int(meta['focal_team']) else -1)
    score_agreement = np.isclose(a['score_diff'][ii], native_score)
    choose = valid[ii] & score_agreement
    score_mismatch = int((valid[ii] & ~score_agreement).sum())
    ii, tt = ii[choose], tt[choose]
    if not len(ii):
        return pd.DataFrame(), {'grid_anchors': initial, 'eligible_anchors': 0, 'score_mismatch_anchors': score_mismatch}
    # Permutation-invariant within-team slots: current y order, all positions,
    # velocities and boost retained; no IDs or post-anchor information required.
    pp = np.asarray(a['players'][ii, :, :7]).copy()
    for lo in (0, 3):
        order = np.argsort(pp[:, lo:lo+3, 1], axis=1, kind='stable')
        pp[:, lo:lo+3] = np.take_along_axis(pp[:, lo:lo+3], order[:, :, None], axis=1)
    x = np.column_stack([a['ball'][ii, :6], pp.reshape(len(ii), -1),
                         a['remaining'][ii], a['score_diff'][ii]])
    df = pd.DataFrame(x, columns=NUMERIC_FEATURES)
    for key in ('replay_id', 'series_id', 'season', 'split', 'focal_team', 'roster_id',
                'opponent_roster_id'):
        df[key] = meta.get(key)
    df['region'] = meta.get('region') or 'unknown'
    df['nominal_grid_time'] = tt
    df['anchor_time'], df['state_time'], df['frame'] = t[ii], t[ii], a['frame'][ii]
    df['last_man_y_own'] = depths['last_man_y_own'][ii]
    df['last_man_behind_ball'] = depths['last_man_behind_ball'][ii]
    if design == 'initiation':
        ids = meta.get('player_ids')
        ids = json.loads(ids) if isinstance(ids, str) else ids
        if ids is None or len(ids) != 6:
            raise ValueError('Initiation requires six stable player IDs in compact metadata')
        df['last_man_index'] = depths['last_man_index'][ii]
        df['last_man_id'] = [str(ids[j]) for j in df['last_man_index']]
        for key, value in initiation_measurement(a, ii, goals, replay).items():
            df[key] = value
        df['baseline_goal_side'] = df['last_man_behind_ball'] > 0

    df['ball_bin'] = np.digitize(df['ball_y'], BALL_EDGES[1:-1])
    df['dose_500uu'] = np.floor(df['last_man_y_own']/500).astype(int)*500
    df['population'] = np.where(df['remaining'] <= 60,
                                np.where(df['score_diff'] == -1, 'late_trailing', 'late_leading'),
                                np.where(df['score_diff'] == -1, 'early_trailing', 'early_leading'))
    if design == 'initiation':
        df.loc[df['score_diff'] == 0, 'population'] = 'tied'
    for key, values in event_labels(t[ii], int(meta['focal_team']), goals, replay,
                                   followup_delay=INITIATION_WINDOW if design == 'initiation' else 0.).items():
        df[key] = values
    if design == 'initiation':
        for key, values in event_labels(t[ii], int(meta['focal_team']), goals, replay,
                                       followup_delay=INITIATION_WINDOW, include_window_goals=True).items():
            df['inclusive_'+key] = values
    return df, {'grid_anchors': initial, 'eligible_anchors': len(df),
                'score_mismatch_anchors': score_mismatch,
                'unknown_demolition_state_anchors': int(np.isnan(a['players'][ii, :, 7]).any(axis=1).sum()),
                'missing_y15': int(df['y15'].isna().sum())}


def anchor_shard(shard, records, goals, by_replay, artifacts, seed, smoke, spacing, scratch, design):
    chunks, counts = [], Counter()
    with tempfile.TemporaryDirectory(prefix='p4-arrays-', dir=scratch or artifacts) as scratch_dir:
        arrays = None
        if not smoke:
            directory = Path(unpack_shard(shard, Path(scratch_dir)))
            arrays = {k: np.load(directory/(k+'.npy'), mmap_mode='r') for k in REQUIRED}
        for meta in records:
            if meta['season'] not in ALLOWED_SEASONS or meta['split'] not in ('train', 'val'):
                raise ValueError('Forbidden split before compact read')
            a = read_slice(meta) if smoke else {
                k: v[int(meta['start']):int(meta['stop'])] for k, v in arrays.items()}
            rid = meta['replay_id']
            replay = dict(by_replay[rid], replay_id=rid)
            gg = goals[goals['replay_id'] == rid]
            frame, diag = anchors_for_replay(meta, a, gg, replay, seed, spacing, design)
            if len(frame):
                chunks.append(frame)
            counts.update(diag)
    return chunks, counts


def build_anchors(pairs, goals, replays, artifacts, seed=42, smoke=False, spacing=1., scratch=None,
                  design='state', workers=1):
    by_replay = replays.set_index('replay_id').to_dict('index')
    by_shard = defaultdict(list)
    for pair in pairs:
        for meta in pair:
            by_shard[meta['_shard']].append(meta)
    tasks = [(shard, records, goals[goals['replay_id'].isin({m['replay_id'] for m in records})],
              by_replay, artifacts, seed, smoke, spacing, scratch, design)
             for shard, records in sorted(by_shard.items())]
    chunks, counts = [], Counter()
    for frames, diag in parallel_tasks(anchor_shard, tasks, workers):
        chunks.extend(frames)
        counts.update(diag)
    result = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    return result, dict(counts)


def freeze_thresholds(df):
    """Equal-series empirical terciles, learned solely from train anchors."""
    train = df[df['split'] == 'train']
    table = {}
    for ball_bin in range(len(BALL_EDGES)-1):
        part = train[train['ball_bin'] == ball_bin]
        if len(part) < 6 or part['series_id'].nunique() < 2:
            table[str(ball_bin)] = {'supported': False, 'rows': len(part), 'series': part['series_id'].nunique()}
            continue
        weights = 1/part.groupby('series_id')['series_id'].transform('size').to_numpy()
        order = np.argsort(part['last_man_y_own'].to_numpy(), kind='stable')
        xx, ww = part['last_man_y_own'].to_numpy()[order], weights[order]
        cdf = (np.cumsum(ww)-.5*ww)/ww.sum()
        lo, hi = np.interp([1/3, 2/3], cdf, xx)
        table[str(ball_bin)] = {'supported': bool(hi > lo), 'lower': lo, 'upper': hi,
                               'rows': len(part), 'series': part['series_id'].nunique()}
    result = df.copy()
    result['treatment'] = np.nan
    for key, threshold in table.items():
        if not threshold['supported']:
            continue
        bb = result['ball_bin'] == int(key)
        result.loc[bb & (result['last_man_y_own'] <= threshold['lower']), 'treatment'] = 0
        result.loc[bb & (result['last_man_y_own'] >= threshold['upper']), 'treatment'] = 1
    return result, {'fit_split': 'train', 'fit_seasons': list(TRAIN_SEASONS),
                    'ball_y_edges': ['-inf', -2560, 0, 2560, 'inf'],
                    'weighting': 'equal series within ball bin', 'bins': table,
                    'middle_or_unsupported_omitted': int(result['treatment'].isna().sum())}


def freeze_initiation(df, delta=DEFAULT_DELTA, control='third', include_early=False, frozen=None):
    """Freeze median eligibility using TRAIN baseline states, never movement/outcomes.

    Delta values are prespecified measurement constants, frozen before validation;
    no goal/outcome is used to select them. Training support is recorded for each.
    """
    if frozen is None:
        train = df[df['split'] == 'train']
        table = {}
        for ball_bin in range(len(BALL_EDGES)-1):
            part = train[train['ball_bin'] == ball_bin]
            entry = {'rows': len(part), 'series': part['series_id'].nunique(), 'supported': False}
            if len(part) >= 6 and part['series_id'].nunique() >= 2:
                weights = 1/part.groupby('series_id')['series_id'].transform('size').to_numpy()
                order = np.argsort(part['last_man_y_own'].to_numpy(), kind='stable')
                xx, ww = part['last_man_y_own'].to_numpy()[order], weights[order]
                entry.update(supported=True, median=float(np.interp(.5, (np.cumsum(ww)-.5*ww)/ww.sum(), xx)))
            table[str(ball_bin)] = entry
    else:
        table = frozen['bins']
    result = df.copy()
    eligible = np.zeros(len(df), bool)
    supported = np.zeros(len(df), bool)
    for key, entry in table.items():
        if entry['supported']:
            bb = (df['ball_bin'] == int(key)).to_numpy()
            supported |= bb
            eligible |= bb & (df['last_man_y_own'].to_numpy() < entry['median']) & df['baseline_goal_side'].to_numpy(bool)
    cutoff = delta/3 if control == 'third' else 0.
    movement = df['displacement_including_early' if include_early else 'displacement_1s'].to_numpy(float)
    observed = np.isfinite(movement)
    allowed = eligible & (include_early | ~df['early_goal'].to_numpy(bool))
    result['baseline_eligible'] = eligible
    result['followup_extra_seconds'] = INITIATION_WINDOW if include_early else 0.
    result['treatment'] = np.nan
    result.loc[allowed & observed & (movement < cutoff), 'treatment'] = 0
    result.loc[allowed & observed & (movement >= delta), 'treatment'] = 1
    if include_early:
        for label in LABELS:
            result[label] = df['inclusive_'+label]
        for horizon in HORIZONS:
            result['goal_id'+str(horizon)] = df['inclusive_goal_id'+str(horizon)]
    counts = {'baseline_eligible': int(eligible.sum()), 'unsupported_baseline_bin': int((~supported).sum()),
              'not_goal_side': int((~df['baseline_goal_side']).sum()),
              'early_goal_baseline_eligible': int((eligible & df['early_goal'].to_numpy(bool)).sum()),
              'early_goal_excluded': 0 if include_early else int((eligible & df['early_goal'].to_numpy(bool)).sum()),
              'unknown_exposure': int((allowed & ~observed).sum()),
              'ambiguous_middle': int((allowed & observed & (movement >= cutoff) & (movement < delta)).sum()),
              'control': int((result['treatment'] == 0).sum()), 'advance': int((result['treatment'] == 1).sum())}
    counts['by_split'] = {split: {'eligible': int((eligible & df['split'].eq(split).to_numpy()).sum()),
                                      'arms': result.loc[df['split'] == split, 'treatment'].value_counts().to_dict()}
                          for split in ('train', 'val')}
    return result, {'fit_split': 'train', 'fit_seasons': list(TRAIN_SEASONS), 'bins': table,
                    'weighting': 'equal series within ball bin among all baseline candidate states; goal-side eligibility applied separately',
                    'delta_uu': delta, 'control_displacement_below_uu': cutoff,
                    'threshold_selection': 'prespecified before validation/outcome access; TRAIN baseline median and TRAIN arm support; no outcome optimization',
                    'include_early_goals': include_early, 'counts': counts}


def feature_matrix(df, train_mask, design='state'):
    regions = sorted(set(df.loc[train_mask, 'region']))
    numeric = NUMERIC_FEATURES + (['last_man_y_own', 'last_man_behind_ball'] if design == 'initiation' else [])
    names = list(numeric) + [f'region={region}' for region in regions]
    columns = [df[numeric].to_numpy(dtype=np.float32)] + [
        (df['region'] == region).to_numpy(dtype=np.float32) for region in regions]
    if design == 'initiation':
        identities = sorted(set(df.loc[train_mask, 'last_man_id']))
        names.extend(f'last_man_id={identity}' for identity in identities)
        columns.extend((df['last_man_id'] == identity).to_numpy(dtype=np.float32) for identity in identities)
    x = np.column_stack(columns)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite baseline controls; no silent covariate imputation')
    return x, names, regions


class ProbabilityModel:
    """Train-only histogram boosting; no internal random validation split."""
    def __init__(self, classes, seed, iterations=80):
        self.classes, self.seed, self.iterations = classes, seed, iterations
        self.model, self.constant = None, None

    def fit(self, x, y, weights):
        observed = np.unique(y)
        if len(observed) == 1:
            self.constant = int(observed[0])
        else:
            self.model = HistGradientBoostingClassifier(
                learning_rate=.06, max_iter=self.iterations, max_leaf_nodes=15,
                max_depth=4, min_samples_leaf=30, l2_regularization=5.,
                early_stopping=False, random_state=self.seed)
            self.model.fit(x, y.astype(int), sample_weight=weights)
        return self

    def predict(self, x):
        result = np.zeros((len(x), self.classes))
        if self.constant is not None:
            result[:, self.constant] = 1
        else:
            result[:, self.model.classes_.astype(int)] = self.model.predict_proba(x)
        return result


def series_weights(series):
    _, inverse, counts = np.unique(np.asarray(series, str), return_inverse=True, return_counts=True)
    w = 1/counts[inverse]
    return w / w.mean()


def fit_predict(train, target, x, a, df, seed, iterations):
    if not df.iloc[train]['split'].eq('train').all():
        raise ValueError('Validation rows forbidden in nuisance fit')
    pred = np.full((len(target), 1+4*6), np.nan)
    diag = {'train_rows': len(train), 'target_rows': len(target),
            'train_series': int(df.iloc[train]['series_id'].nunique()), 'models': {}}
    if not len(train) or len(np.unique(a[train])) < 2:
        diag['failure'] = 'training treatment arm missing'
        return pred, diag
    weights = series_weights(df.iloc[train]['series_id'])
    model = ProbabilityModel(2, seed, iterations).fit(x[train], a[train], weights)
    pred[:, 0] = model.predict(x[target])[:, 1]
    for j, label in enumerate(('y5', 'y10', 'y15', 'ypast10')):
        yy = df[label].to_numpy(float)
        for arm in (0, 1):
            use = train[(a[train] == arm) & np.isfinite(yy[train])]
            key = f'{label}/arm{arm}'
            diag['models'][key] = {'rows': len(use), 'classes': np.unique(yy[use]).tolist()}
            if not len(use):
                continue
            model = ProbabilityModel(3, seed+j*2+arm+1, iterations).fit(
                x[use], yy[use], series_weights(df.iloc[use]['series_id']))
            pred[:, 1+j*6+arm*3:1+j*6+arm*3+3] = model.predict(x[target])
    return pred, diag


def nuisance_predictions(df, folds=3, seed=42, iterations=80, design='state', workers=1):
    train_mask = (df['split'] == 'train').to_numpy()
    train = np.flatnonzero(train_mask)
    val = np.flatnonzero(~train_mask)
    x, feature_names, regions = feature_matrix(df, train_mask, design)
    a = df['treatment'].to_numpy(int)
    pred = np.full((len(df), 25), np.nan)
    series = sorted(df.iloc[train]['series_id'].unique(), key=lambda s: stable_hash(f'{seed}:{s}:fold'))
    folds = min(folds, len(series))
    manifest = {'scheme': 'grouped OOF in train; final all-train fit predicts 2025; no validation fitting',
                'train_seasons': list(TRAIN_SEASONS), 'val_season': VAL_SEASON,
                'folds': folds, 'feature_names': feature_names, 'training_region_levels': regions,
                'algorithm': 'HistGradientBoostingClassifier', 'max_iter': iterations,
                'hyperparameters': {'learning_rate': .06, 'max_leaf_nodes': 15, 'max_depth': 4,
                                    'min_samples_leaf': 30, 'l2_regularization': 5., 'early_stopping': False},
                'fits': [], 'validation_rows_used_in_fit': 0}
    tasks, destinations = [], []
    if design == 'initiation':
        known = set(df.loc[train_mask, 'last_man_id'])
        manifest['unknown_validation_last_man_id_rows'] = int((~df.loc[~train_mask, 'last_man_id'].isin(known)).sum())
    if folds >= 2:
        assignment = {s: i % folds for i, s in enumerate(series)}
        row_fold = df['series_id'].map(assignment).fillna(-1).to_numpy(int)
        manifest['series_fold_assignment'] = assignment
        for fold in range(folds):
            heldout = np.flatnonzero(train_mask & (row_fold == fold))
            fit = np.flatnonzero(train_mask & (row_fold != fold))
            assert not set(df.iloc[fit]['series_id']) & set(df.iloc[heldout]['series_id'])
            tasks.append((fit, heldout, x, a, df, seed+fold*100, iterations))
            destinations.append((heldout, {'fold': fold, 'target': 'train_oof'}))
    else:
        manifest['train_oof_failure'] = 'fewer than two training series'
    if len(val):
        assert not set(df.iloc[train]['series_id']) & set(df.iloc[val]['series_id'])
        tasks.append((train, val, x, a, df, seed+10000, iterations))
        destinations.append((val, {'target': 'val'}))
    if tasks:
        for (pp, diag), (indices, context) in zip(parallel_tasks(fit_predict, tasks, min(workers, len(tasks)),
                    max(1, workers//len(tasks))), destinations):
            pred[indices] = pp
            manifest['fits'].append(dict(diag, **context))
    return pred, x, manifest


def cluster_bootstrap(contributions, series, repeats, seed):
    """Resample whole series, equivalently their within-series vector means.

    All outcomes/arms use identical draws. Nuisance functions remain fixed: this
    is a cluster bootstrap of cross-fitted/externally fitted influence scores,
    not an expensive nuisance-refit bootstrap. Each series gets equal weight.
    """
    frame = pd.DataFrame(contributions)
    frame['series'] = np.asarray(series)
    means = frame.groupby('series', sort=True).mean().to_numpy()
    estimate = means.mean(axis=0)
    if len(means) < 2 or repeats < 2:
        return estimate, np.full((2, means.shape[1]), np.nan), np.empty((0, means.shape[1]))
    rng = np.random.default_rng(seed)
    draws = np.empty((repeats, means.shape[1]))
    for lo in range(0, repeats, 128):
        count = min(128, repeats-lo)
        idx = rng.integers(len(means), size=(count, len(means)))
        draws[lo:lo+count] = means[idx].mean(axis=1)
    return estimate, np.quantile(draws, [.025, .975], axis=0), draws


def e_value(rr):
    if not np.isfinite(rr) or rr <= 0:
        return None
    rr = max(rr, 1/rr)
    return float(rr + np.sqrt(rr*(rr-1)))


def risk_ratio_summary(r0, r1, draws0, draws1):
    if not (0 < r0 <= 1 and 0 < r1 <= 1):
        return {'rr': None, 'e_value': None, 'reason': 'DR risks outside (0,1]; not clipped for RR'}
    good = (draws0 > 0) & (draws0 <= 1) & (draws1 > 0) & (draws1 <= 1)
    rr = r1/r0
    out = {'rr': rr, 'e_value': e_value(rr), 'valid_bootstrap_replicates': int(good.sum()),
           'interpretation': 'RR sensitivity descriptor only; cannot establish exchangeability or cure failed overlap'}
    if len(draws0) >= 20 and good.all():
        ci = np.quantile(draws1[good]/draws0[good], [.025, .975])
        nearest = 1. if ci[0] <= 1 <= ci[1] else (ci[0] if ci[0] > 1 else ci[1])
        out.update(ci95=ci, e_value_ci_limit=e_value(nearest))
    else:
        out['ci95'] = None
        out['e_value_ci_limit'] = None
    return out


def balance_diagnostics(x, a, e, series, names):
    base = series_weights(series)
    e = np.clip(e, 1e-6, 1-1e-6)
    weights = base * np.where(a == 1, 1/e, 1/(1-e))
    records, summaries = [], {}
    if len(np.unique(a)) < 2:
        return {'failure': 'one observed arm', 'covariates': []}
    moments = []
    for arm in (0, 1):
        sel = a == arm
        w, bw, xx = weights[sel], base[sel], x[sel]
        mean = np.average(xx, axis=0, weights=bw)
        variance = np.average((xx-mean)**2, axis=0, weights=bw)
        adjusted = np.average(xx, axis=0, weights=w)
        moments.append((mean, variance, adjusted))
        sw = pd.DataFrame({'series': np.asarray(series)[sel], 'w': w}).groupby('series')['w'].sum().to_numpy()
        summaries[str(arm)] = {'rows': int(sel.sum()), 'series': len(sw),
                               'anchor_weight_ess': float(w.sum()**2/np.sum(w*w)),
                               'series_weight_ess': float(sw.sum()**2/np.sum(sw*sw)),
                               'max_inverse_probability_weight': float((w/bw).max())}
    sd = np.sqrt((moments[0][1]+moments[1][1])/2)
    for j, name in enumerate(names):
        def standardized(delta):
            return float(delta/sd[j]) if sd[j] > 1e-12 else (0. if abs(delta) < 1e-12 else None)
        records.append({'feature': name, 'before': standardized(moments[1][0][j]-moments[0][0][j]),
                        'after': standardized(moments[1][2][j]-moments[0][2][j])})
    values = [abs(r['after']) for r in records if r['after'] is not None]
    return {'arms': summaries, 'covariates': records, 'max_abs_smd_after': max(values, default=None),
            'undefined_smd_count': sum(r['after'] is None for r in records),
            'balanced_below_0_1': bool(values and max(values) < OVERLAP_GATES['maximum_smd'] and all(r['after'] is not None for r in records))}


def estimate_contrast(df, pred, x, feature_names, label, trim, repeats, seed, design='state'):
    label_index = {'y5': 0, 'y10': 1, 'y15': 2, 'ypast10': 3}[label]
    y = df[label].to_numpy(float)
    a = df['treatment'].to_numpy(int)
    e = pred[:, 0]
    m = pred[:, 1+6*label_index:1+6*label_index+6].reshape(-1, 2, 3)
    complete = np.isfinite(y) & np.isfinite(e) & np.isfinite(m).all(axis=(1, 2))
    keep = complete & (e >= trim) & (e <= 1-trim)
    result = {'status': 'insufficient_support', 'outcome': label, 'trim': [trim, 1-trim],
              'input_rows': len(df), 'complete_rows': int(complete.sum()), 'retained_rows': int(keep.sum()),
              'trim_fraction': float(1-keep.sum()/max(1, complete.sum())),
              'causal_identification': False, 'structural_positivity': design == 'initiation',
              'estimand': ('observational one-second survivor landmark contrast among retained eligible baseline states; advance versus stay/retreat'
                           if design == 'initiation' else 'exploratory model-dependent numerical DR state contrast; no identified intervention'),
              'causal_assumptions': 'No unmeasured confounding, consistency of the movement proxy, noninformative landmark selection/measurement/censoring, and independence across series. Observational, not randomized.',
              'numeric_propensity_clip_epsilon': 1e-6,
              'missing_outcome_rows': int(np.isnan(y).sum()),
              'censoring': 'Complete observed labels only; no independent-censoring assumption asserted. Missing-label worst-case risk bounds are descriptive.'}
    result['censoring_sensitivity'] = {}
    for arm in (0, 1):
        sel = a == arm
        if sel.any():
            yy = y[sel]
            ww = series_weights(df.loc[sel, 'series_id'])
            missing = np.average(~np.isfinite(yy), weights=ww)
            lower_for = np.average(yy == 1, weights=ww)
            lower_against = np.average(yy == 2, weights=ww)
            result['censoring_sensitivity'][str(arm)] = {'missing_fraction': missing,
                'for_risk_bounds': [lower_for, lower_for+missing],
                'against_risk_bounds': [lower_against, lower_against+missing],
                'net_gd_bounds': [lower_for-lower_against-missing, lower_for-lower_against+missing]}
    if complete.any():
        base = series_weights(df.loc[complete, 'series_id'])
        raw_e = e[complete]
        result['propensity_before_trim'] = {
            'equal_series_fraction_outside_0_05_0_95': np.average((raw_e < .05) | (raw_e > .95), weights=base),
            'equal_series_fraction_numerically_clipped': np.average((raw_e < 1e-6) | (raw_e > 1-1e-6), weights=base),
            'max_observed_inverse_probability_weight_unclipped': float(np.max(1/np.maximum(
                np.where(a[complete] == 1, raw_e, 1-raw_e), np.finfo(float).tiny))),
            'histogram_by_arm': {str(arm): np.histogram(e[complete & (a == arm)], bins=np.linspace(0,1,11))[0].tolist()
                                 for arm in (0,1)}}
    if keep.sum() == 0:
        return result
    d = df.loc[keep].reset_index(drop=True)
    a, y, m = a[keep], y[keep], m[keep]
    e = np.clip(e[keep], 1e-6, 1-1e-6)
    series = d['series_id'].to_numpy()
    result['series'] = int(d['series_id'].nunique())
    result['arm_series'] = {str(arm): int(d.loc[a == arm, 'series_id'].nunique()) for arm in (0, 1)}
    result['overlap'] = {str(arm): {'quantiles': np.quantile(e[a == arm], [0, .01, .05, .25, .5, .75, .95, .99, 1]).tolist()
                                      if np.any(a == arm) else [],
                                      'histogram': np.histogram(e[a == arm], bins=np.linspace(0, 1, 11))[0].tolist()}
                         for arm in (0, 1)}
    result['balance'] = balance_diagnostics(x[keep], a, e, series, feature_names)
    if len(np.unique(a)) < 2 or len(np.unique(series)) < 2:
        result['reason'] = 'Need both arms and at least two retained series'
        return result
    actual = np.column_stack([y == 1, y == 2]).astype(float)
    psi = []
    for arm in (0, 1):
        mu = m[:, arm, 1:3]
        propensity = e if arm else 1-e
        psi.append(mu + ((a == arm)/propensity)[:, None]*(actual-mu))
    # r0_for,r0_against,r1_for,r1_against,RD_for,RD_against,GD0,GD1,deltaGD.
    values = np.column_stack([psi[0], psi[1], psi[1]-psi[0],
                              psi[0][:, 0]-psi[0][:, 1], psi[1][:, 0]-psi[1][:, 1],
                              (psi[1][:, 0]-psi[1][:, 1])-(psi[0][:, 0]-psi[0][:, 1])])
    point, interval, draws = cluster_bootstrap(values, series, repeats, seed)
    names = ['deep_for', 'deep_against', 'advanced_for', 'advanced_against',
             'difference_for', 'difference_against', 'deep_net_gd', 'advanced_net_gd', 'difference_net_gd']
    if design == 'initiation':
        names = [name.replace('deep_', 'stay_').replace('advanced_', 'advance_') for name in names]
    result['adjusted'] = {name: {'estimate': point[j], 'ci95': interval[:, j]} for j, name in enumerate(names)}
    result['exposure_weighted_secondary'] = dict(zip(names, values.mean(axis=0)))
    result['naive'] = {'target': 'Each arm averages its arm-present series; arm targets may differ from the common retained-series DR target'}
    for arm in (0, 1):
        mean, ci, _ = cluster_bootstrap(actual[a == arm], series[a == arm], repeats, seed+arm+11)
        result['naive'][str(arm)] = {'for': mean[0], 'against': mean[1], 'net_gd': mean[0]-mean[1],
                                    'ci95_for': ci[:, 0], 'ci95_against': ci[:, 1]}
    result['naive']['difference_for'] = result['naive']['1']['for']-result['naive']['0']['for']
    result['naive']['difference_against'] = result['naive']['1']['against']-result['naive']['0']['against']
    result['naive']['difference_net_gd'] = result['naive']['1']['net_gd']-result['naive']['0']['net_gd']
    for j, outcome in enumerate(OUTCOMES):
        result[f'rr_{outcome}'] = risk_ratio_summary(point[j], point[2+j], draws[:, j], draws[:, 2+j])
    unique = {}
    if label != 'ypast10':
        goal_id = d['goal_id'+label[1:]].to_numpy()
        for arm in (0, 1):
            for code, outcome in enumerate(OUTCOMES, 1):
                unique[f'{arm}_{outcome}'] = len(set(goal_id[(a == arm) & (y == code)])- {''})
    result['unique_goals_by_arm'] = unique
    result['feasibility_gates'] = {'at_least_50_series': result['series'] >= OVERLAP_GATES['minimum_series'],
                                   'at_least_20_series_each_arm': min(result['arm_series'].values()) >= OVERLAP_GATES['minimum_arm_series'],
                                   'at_least_50_unique_goals_each_arm_outcome': bool(unique) and min(unique.values()) >= OVERLAP_GATES['minimum_unique_goals'],
                                   'smd_below_0_1': result['balance'].get('balanced_below_0_1', False),
                                   'structural_positivity': design == 'initiation'}
    balance = result['balance']
    result['overlap_gates'] = {
        'extreme_mass_at_most_0_1': result['propensity_before_trim']['equal_series_fraction_outside_0_05_0_95'] <= OVERLAP_GATES['maximum_extreme_mass'],
        'trim_fraction_at_most_0_2': result['trim_fraction'] <= OVERLAP_GATES['maximum_trim_fraction'],
        'anchor_ess_at_least_100_each_arm': min(v['anchor_weight_ess'] for v in balance['arms'].values()) >= OVERLAP_GATES['minimum_anchor_ess'],
        'series_ess_at_least_20_each_arm': min(v['series_weight_ess'] for v in balance['arms'].values()) >= OVERLAP_GATES['minimum_series_ess'],
        'all_smd_below_0_1': balance['balanced_below_0_1']}
    result['causal_identification'] = bool(design == 'initiation' and label != 'ypast10' and
                                          all(result['feasibility_gates'].values()) and all(result['overlap_gates'].values()))
    result['status'] = ('computed_observational_contrast_overlap_gates_passed_conditional_on_assumptions'
                        if result['causal_identification'] else 'computed_association_causal_gate_failed')
    if label == 'ypast10':
        result['negative_control'] = {'events': int(np.count_nonzero(y)), 'degenerate': bool(np.count_nonzero(y) == 0),
                                      'caution': 'Behavior may respond to past goals; absence of signal does not validate exchangeability'}
    if label != 'ypast10':
        horizon = int(label[1:]) + (float(d['followup_extra_seconds'].iloc[0]) if 'followup_extra_seconds' in d else 0.)
        result['followup_duration_seconds'] = horizon
        result['net_gd_per_horizon_second'] = point[8]/horizon
        result['net_gd_per_horizon_second_definition'] = 'delta expected first-goal differential / fixed horizon; not pushed-up exposure seconds'
    return result


def predictive_diagnostics(df, predictions):
    result = {}
    for j, label in enumerate(('y5', 'y10', 'y15', 'ypast10')):
        yy = df[label].to_numpy(float)
        a = df['treatment'].to_numpy(int)
        m = predictions[:, 1+6*j:1+6*j+6].reshape(-1, 2, 3)
        pp = m[np.arange(len(df)), a]
        keep = np.isfinite(yy) & np.isfinite(pp).all(axis=1)
        if not keep.any():
            result[label] = {'status': 'no_predictions'}
            continue
        y, p = yy[keep].astype(int), pp[keep]
        weights = series_weights(df.loc[keep, 'series_id'])
        item = {'rows': len(y), 'log_loss': log_loss(y, p, labels=[0, 1, 2], sample_weight=weights),
                'brier_for': brier_score_loss(y == 1, p[:, 1], sample_weight=weights),
                'brier_against': brier_score_loss(y == 2, p[:, 2], sample_weight=weights),
                'reliability': {}}
        for code, outcome in enumerate(OUTCOMES, 1):
            bins = np.minimum((p[:, code]*10).astype(int), 9)
            item['reliability'][outcome] = [{'bin': b, 'n': int((bins == b).sum()),
                                           'predicted': np.average(p[bins == b, code], weights=weights[bins == b]),
                                           'observed': np.average((y[bins == b] == code), weights=weights[bins == b])}
                                          for b in range(10) if (bins == b).any()]
        result[label] = item
    return result


def dose_curve(df, repeats, seed):
    """500-uu observed risk curve, including omitted middle; never causal dose."""
    rows = []
    for (population, dose), part in df.groupby(['population', 'dose_500uu'], sort=True):
        for horizon in HORIZONS:
            part_h = part[part[f'y{horizon}'].notna()]
            if len(part_h) == 0:
                continue
            y = part_h[f'y{horizon}'].to_numpy()
            values = np.column_stack([y == 1, y == 2, (y == 1).astype(int)-(y == 2)])
            mean, ci, _ = cluster_bootstrap(values, part_h['series_id'], repeats, seed)
            rows.append({'population': population, 'dose_lower_uu': int(dose), 'dose_upper_uu': int(dose)+500,
                         'horizon': horizon, 'anchors': len(part_h), 'series': part_h['series_id'].nunique(),
                         'for': mean[0], 'against': mean[1], 'net_gd': mean[2], 'ci95': ci,
                         'method': 'equal-series observed risk; descriptive dose association, no dose intervention'})
    return rows


def analyze_population(sub, pred, x, nuisance, repeats, seed, design, secondary_repeats):
    if not len(sub):
        return {'status': 'no_anchors'}
    block = {'predictive': predictive_diagnostics(sub, pred), 'contrasts': {}}
    for label in ('y10', 'y5', 'y15', 'ypast10'):
        draws = secondary_repeats if label in ('y5', 'y15') else repeats
        for trim in (0., .05, .1):
            key = f'{label}/trim_{trim:.2f}'
            block['contrasts'][key] = estimate_contrast(
                sub, pred, x, nuisance['feature_names'], label, trim, draws, seed, design)
            block['contrasts'][key]['bootstrap_repeats'] = draws
    return block


def analyze(df, pred, x, nuisance, repeats, seed, design='state', workers=1, secondary_repeats=None):
    tasks, keys = [], []
    for split in ('train', 'val'):
        populations = ['late_trailing', 'late_leading', 'early_trailing', 'early_leading']
        if design == 'initiation':
            populations += ['tied', 'early_play']
        for population in populations:
            pp = (df['remaining'] > 60).to_numpy() if population == 'early_play' else (df['population'] == population).to_numpy()
            mask = (df['split'] == split).to_numpy() & pp
            sub = df.loc[mask].reset_index(drop=True)
            keys.append(f'{split}/{population}')
            tasks.append((sub, pred[mask], x[mask], nuisance, repeats,
                          seed+stable_hash(f'{split}:{population}') % 100000, design, secondary_repeats or repeats))
    return dict(zip(keys, parallel_tasks(analyze_population, tasks, workers)))


def self_test():
    """Synthetic contract tests; no replay or filesystem data are opened."""
    goals = pd.DataFrame({'time': [10., 15., 22.], 'scoring_team': [0, 1, 0], 'frame': [300, 450, 660]})
    replay = {'replay_id': 'synthetic', 'observed_start_time': 0., 'observed_end_time': 25.,
              'terminal_verified': False, 'terminal_time': None, 'regulation_end_time': 18.,
              'gap_start_times': '[]', 'gap_end_times': '[]'}
    labels = event_labels(np.array([0., 10., 15., 20., 24.]), 0, goals, replay)
    assert labels['y10'][0] == 1  # closed right endpoint
    assert labels['y5'][1] == 2  # open left: goal at t=10 not counted
    assert labels['y10'][2] == 1  # follow across regulation end, not censor
    assert labels['y5'][3] == 1 and np.isnan(labels['y5'][4])  # unknown EOF
    opposite = event_labels(np.array([10.]), 1, goals, replay)
    assert opposite['y5'][0] == 1  # same event, opposing focal identity
    terminal = dict(replay, terminal_verified=True, terminal_time=25.)
    assert event_labels(np.array([24.]), 0, goals, terminal)['y15'][0] == 0
    gap = dict(replay, gap_start_times='[11.0]', gap_end_times='[13.0]')
    assert np.isnan(event_labels(np.array([10.]), 0, goals, gap)['y10'][0])
    assert event_labels(np.array([0.]), 0, goals, gap)['y10'][0] == 1
    assert np.isnan(event_labels(np.array([15.]), 0, goals, gap)['ypast10'][0])
    t = np.arange(0, 31, .1)
    ii, tt = fixed_anchor_indices(t, 'same-series', 42)
    jj, uu = fixed_anchor_indices(t, 'same-series', 42)
    assert np.array_equal(ii, jj) and np.array_equal(tt, uu)
    assert np.all(t[ii] <= tt) and np.allclose(np.diff(tt), 1)
    mean, _, _ = cluster_bootstrap(np.r_[np.zeros(100), 1.][:, None], ['a']*100+['b'], 50, 7)
    assert mean[0] == .5  # equal series, not exposure weighted
    assert e_value(1.) == 1. and np.isclose(e_value(2.), 2+np.sqrt(2))
    example = pd.DataFrame({'split': ['train']*12+['val'], 'series_id': ['a']*6+['b']*6+['v'],
                            'ball_bin': [0]*13, 'last_man_y_own': list(range(12))+[999999.]})
    _, threshold1 = freeze_thresholds(example)
    example.loc[12, 'last_man_y_own'] = -999999
    _, threshold2 = freeze_thresholds(example)
    assert threshold1['bins'] == threshold2['bins']
    features = pd.DataFrame(np.zeros((3, len(NUMERIC_FEATURES))), columns=NUMERIC_FEATURES)
    features['region'] = ['A', 'B', 'future-region']
    _, names, regions = feature_matrix(features, np.array([True, True, False]))
    assert regions == ['A', 'B'] and 'region=future-region' not in names
    try:
        fit_predict(np.array([0]), np.array([1]), np.zeros((2, 1)), np.zeros(2),
                    pd.DataFrame({'split': ['val', 'val']}), 42, 1)
    except ValueError as error:
        assert 'Validation rows' in str(error)
    else:
        raise AssertionError('Validation fit guard failed')
    for forbidden in ('/tmp/rlcs-2026/compact.npz', '/tmp/test/compact.npz'):
        try:
            guard_path(forbidden)
        except ValueError:
            pass
        else:
            raise AssertionError('2026/test path guard failed')
    from .pushup_dr_tests import run_tests
    run_tests()
    print(json.dumps({'self_test': 'passed', 'checks': ['first-goal endpoints', 'competing identities',
                     'terminal and gap censoring', 'regulation end not censoring', 'series grid',
                     'equal-series bootstrap', 'RR E-value', 'train-only thresholds/regions',
                     'validation fit rejected', '2026/test path guards']}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', choices=('state', 'initiation'), default='state')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--delta', type=float, default=DEFAULT_DELTA)
    parser.add_argument('--delta-sensitivities', type=float, nargs='*', default=list(DEFAULT_DELTA_SENSITIVITIES))
    parser.add_argument('--secondary-bootstrap', type=int, default=None, help='5/15-second horizons only; primary stays at --bootstrap')
    parser.add_argument('--compact', type=Path, default=None)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--scratch', type=Path, help='Temporary one-shard unpack/mmap directory')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--out', type=Path, default=Path('results/pushup_dr.json'))
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--state-map', type=Path, default=Path('state_map_rlcs.json'))
    parser.add_argument('--max-replays', type=int)
    parser.add_argument('--replay-ids', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--folds', type=int, default=3)
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--iterations', type=int, default=80)
    parser.add_argument('--anchor-spacing', type=float, default=1., choices=(1., 10.))
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.artifacts is None:
        parser.error('--artifacts is required outside --self-test')
    if args.scratch is not None:
        guard_path(args.scratch).mkdir(parents=True, exist_ok=True)
    if args.workers < 1 or args.delta <= 0 or any(d <= 0 for d in args.delta_sensitivities):
        parser.error('workers and displacement thresholds must be positive')
    if args.secondary_bootstrap is not None and args.secondary_bootstrap < 2:
        parser.error('secondary-bootstrap must be >=2')
    if args.max_replays is not None and args.max_replays > 10:
        parser.error('Bounded login smoke is capped at ten replays; omit --max-replays for batch')
    if args.max_replays is not None and args.workers != 1:
        parser.error('Login smoke requires --workers 1')
    if args.design == 'initiation' and args.out == Path('results/pushup_dr.json'):
        args.out = Path('results/pushup_dr_initiation.json')
    if args.folds < 2 or args.bootstrap < 2 or args.iterations < 1:
        parser.error('folds/bootstrap >=2 and iterations >=1 required')
    started = time.perf_counter()
    compact = guard_path(args.compact or (MEDIUM if MEDIUM.exists() else SMALL))
    artifacts = guard_path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    if artifacts.resolve() == compact.resolve() or compact.resolve() in artifacts.resolve().parents:
        raise ValueError('P4 artifacts must not modify input compact')
    pairs, inventory = metadata_inventory(compact)
    pairs = select_pairs(pairs, args.max_replays, args.replay_ids, args.seed)
    if not pairs:
        raise ValueError('No allowed replays selected')
    selected = [row for pair in pairs for row in pair]
    ids = sorted({row['replay_id'] for row in selected})
    atomic_json(artifacts/'selected_replays.json', ids)
    clock = time.perf_counter()
    goals, replays = build_events(selected, artifacts, data_root=guard_path(args.data_root),
                                  state_map_path=guard_path(args.state_map))
    events_seconds = time.perf_counter()-clock
    clock = time.perf_counter()
    anchors, anchor_audit = build_anchors(pairs, goals, replays, artifacts, args.seed,
                                         smoke=args.max_replays is not None, spacing=args.anchor_spacing, scratch=args.scratch,
                                         design=args.design, workers=args.workers)
    anchor_seconds = time.perf_counter()-clock
    code_root = Path(__file__).resolve().parents[2]
    code_hashes = {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                   for name in ('pushup_dr.py', 'events.py', 'pressure.py', 'screen.py', 'data.py')}
    try:
        git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=code_root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = None
    details = {'source_provenance': {'git_head_at_run': git_head, 'source_sha256': code_hashes,
               'state_map_sha256': hashlib.sha256(guard_path(args.state_map).read_bytes()).hexdigest(),
               'extraction_manifest_sha256': hashlib.sha256(guard_path(compact/'extraction.json').read_bytes()).hexdigest(),
               'input_shard_stat': {str(path): {'bytes': Path(path).stat().st_size, 'mtime_ns': Path(path).stat().st_mtime_ns}
                                    for path in sorted({row['_shard'] for row in selected})}},
               'parameters': vars(args),
               'design': args.design,
               'analysis': ('P4 C2 state-risk association and numerical DR diagnostics' if args.design == 'state' else
                            'P4 C3 one-second fixed-defender initiation; survivor-selected observational landmark analysis'),
               'causal_effect_identified': False, 'causal_identification': False,
               'structural_positivity_failure': ('Treatment is a deterministic function of included own player y and ball y. Approximate fitted overlap cannot restore positivity.' if args.design == 'state' else None),
               'causal_assumptions': 'Observational: no unmeasured confounding, consistency, noninformative landmark selection/measurement/censoring, and independence across series. Passing overlap gates is necessary, never proof of these assumptions.',
               'overlap_gate_thresholds': OVERLAP_GATES,
               'live_3v3_definition': 'Six finite position/velocity/boost tracks; known demolished and past-stale tracks excluded. Unknown demolition duration remains unverified; no claim of audited 3v3 availability.',
               'input_compact': str(compact), 'selected_replay_count': len(ids),
               'selected_replay_sha256': hashlib.sha256('\n'.join(ids).encode()).hexdigest(),
               'smoke_sample': args.max_replays is not None,
               'series_completeness': 'All available selected compact members in batch; external complete-series membership is not certified. Bounded smoke may select partial series and is feasibility only.',
               'test_2026_opened': False, 'allowed_seasons': list(ALLOWED_SEASONS),
               'inventory': inventory, 'anchor_audit': anchor_audit,
               'event_audit': {'validated_replays': int(replays['validated'].sum()),
                               'replays': len(replays), 'goals': len(goals)},
               'anchor_grid': {'spacing_seconds': args.anchor_spacing, 'hash_unit': 'series',
                               'state': 'fixed nominal grid snapped down to last compact frame (<=0.15s); actual state time is exposure/eligibility/followup origin',
                               'population': ('regulation, exact score +/-1, 10-180 seconds remaining' if args.design == 'state' else
                                              'regulation, score -1/0/+1, 10-180 s; goal-side and below TRAIN median L within ball-y bin at t')},
               'outcomes': ('(t,t+T] first focal/opponent goal, T=5/10/15; certified game end absorbing; regulation end does not censor; unknown truncation missing; live/reset boundaries do not censor goals' if args.design == 'state' else
                            '(t+1,t+1+T] first goal, T=10 primary 5/15 secondary; primary excludes/counts any goal in (t,t+1]; early-goal sensitivity includes first goal in (t,t+1+T] with movement truncated at pre-goal live frame'),
               'bootstrap': {'repeats': args.bootstrap, 'secondary_horizon_repeats': args.secondary_bootstrap or args.bootstrap, 'unit': 'whole series',
                              'weighting': 'within-series mean then equal-series mean',
                              'nuisances': 'fixed OOF or external predictions; cluster resampling of influence contributions; no nuisance refit; conditional on training data and frozen thresholds'},
               'multiplicity': 'Exploratory 2025 development; late-trailing 10s primary. No confirmatory p-values; 5/15s, strata, thresholds, strict-retreat and early-goal inclusion are sensitivities.',
               'timing_seconds': {'events': events_seconds, 'anchors': anchor_seconds}}
    metrics = {'replays': len(ids), 'validated_replays': int(replays['validated'].sum()),
               'anchors': len(anchors), 'causal_identification_gate_passed': 0.}
    if len(anchors):
        variants = [('primary', args.delta, 'third', False)]
        if args.design == 'initiation':
            variants += [(f'delta_{delta:g}', delta, 'third', False) for delta in args.delta_sensitivities if delta != args.delta]
            variants += [('strict_retreat', args.delta, 'retreat', False),
                         ('including_early_goals', args.delta, 'third', True)]
        details['sensitivity_analyses'] = {}
        frozen = None
        for variant, delta, control, early in variants:
            if args.design == 'state':
                assigned, thresholds = freeze_thresholds(anchors)
            else:
                assigned, thresholds = freeze_initiation(anchors, delta, control, early, frozen)
                if frozen is None:
                    frozen = thresholds
            report = details if variant == 'primary' else {}
            report['thresholds'] = thresholds
            if early:
                report['exposure_caution'] = ('Sensitivity changes treatment to displacement over the observed pre-goal portion of the 1s window for early goals. '
                    'It includes early goals as outcomes, never uses reset coordinates, and cannot recover unobserved full-second counterfactual movement. '
                    'Unknown and ambiguous exposure remains counted, not silently assigned to control.')
            destination = artifacts if variant == 'primary' else artifacts/variant
            destination.mkdir(parents=True, exist_ok=True)
            assigned.to_parquet(destination/'anchors.parquet', index=False)
            extremes = assigned[assigned['treatment'].notna()].reset_index(drop=True)
            if args.design == 'state':
                details['dose_curve_val'] = dose_curve(assigned[assigned['split'] == 'val'], args.bootstrap, args.seed)
            if len(extremes) and (extremes['split'] == 'train').any():
                clock = time.perf_counter()
                pred, x, nuisance = nuisance_predictions(extremes, args.folds, args.seed, args.iterations,
                                                         args.design, args.workers)
                nuisance_seconds = time.perf_counter()-clock
                report['nuisances'] = nuisance
                np.savez_compressed(destination/'nuisance_predictions.npz', predictions=pred)
                extremes[['replay_id', 'series_id', 'focal_team', 'anchor_time', 'split', 'population', 'treatment']].to_parquet(
                    destination/'prediction_rows.parquet', index=False)
                clock = time.perf_counter()
                report['estimates'] = analyze(extremes, pred, x, nuisance, args.bootstrap, args.seed,
                                             args.design, args.workers, args.secondary_bootstrap)
                inference_seconds = time.perf_counter()-clock
                for phase, seconds in [('nuisances', nuisance_seconds), ('inference', inference_seconds)]:
                    details['timing_seconds'][phase] = details['timing_seconds'].get(phase, 0.) + seconds
                if variant != 'primary':
                    report['timing_seconds'] = {'nuisances': nuisance_seconds, 'inference': inference_seconds}
                main_result = report['estimates'].get('val/late_trailing', {}).get('contrasts', {}).get('y10/trim_0.05', {})
                report['status'] = main_result.get('status', 'insufficient_primary_validation_support')
                if variant == 'primary':
                    for key in ('difference_for', 'difference_against', 'difference_net_gd'):
                        value = main_result.get('adjusted', {}).get(key, {}).get('estimate')
                        if value is not None and np.isfinite(value):
                            metrics['exploratory_dr_'+key] = value
                    identified = bool(main_result.get('causal_identification', False))
                    details['causal_effect_identified'] = identified
                    details['causal_identification'] = identified
                    metrics['causal_identification_gate_passed'] = float(identified)
            else:
                report['status'] = 'insufficient_training_treatment_support'
            if variant != 'primary':
                details['sensitivity_analyses'][variant] = report
    else:
        details['status'] = 'no_eligible_anchors'
    details['timing_seconds']['total'] = time.perf_counter()-started
    result = {'method': 'train-frozen HGB / series-cross-fitted AIPW '+args.design+' audit',
              'task': 'pushup_dr', 'split': 'val', 'is_baseline': False,
              'metrics': metrics, 'details': details, 'updated': now(),
              'notes': ('FEASIBILITY SMOKE ONLY: bounded replay sample, no research conclusion or identified causal effect.'
                        if args.max_replays is not None else
                        ('Exploratory development model-dependent contrasts; structural positivity fails for depth treatment with full geometry controls.' if args.design == 'state' else
                         'Observational initiation landmark contrasts; no-unmeasured-confounding and noninformative selection assumptions remain unverified even when overlap gates pass.'))}
    atomic_json(guard_path(args.out), result)
    atomic_json(artifacts/('pushup_dr_initiation.json' if args.design == 'initiation' else 'pushup_dr.json'), result)
    print(json.dumps({'status': details['status'], 'metrics': metrics,
                      'timing_seconds': details['timing_seconds'], 'output': str(args.out)}))
    return result


if __name__ == '__main__':
    main()
