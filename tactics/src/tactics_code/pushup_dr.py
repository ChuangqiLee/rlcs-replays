"""Development-only defensive-depth risk contrasts and DR diagnostics.

The requested exposure is a state, not the initiation treatment in P4_plan C3.
Because all six current player coordinates are required controls, depth-tercile
assignment is deterministic given X. We compute the requested numerical AIPW
contrasts for audit, but ALWAYS fail the causal positivity gate. Their labels,
JSON and dose curves describe exploratory state-outcome associations. A fitted
propensity in (0,1) cannot repair this structural identification failure.

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


def event_labels(anchor_times, focal_team, goals, replay):
    """Competing first-goal labels; unknown truncated tails remain missing."""
    g = goals.sort_values('time')
    gt = g['time'].to_numpy(float)
    teams = g['scoring_team'].to_numpy(int)
    frames = g['frame'].to_numpy(int)
    n = len(anchor_times)
    after = np.searchsorted(gt, anchor_times, side='right')
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
        deadline = np.minimum(anchor_times+horizon, stop)
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


def anchors_for_replay(meta, a, goals, replay, seed, spacing=1.):
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
    valid &= np.isin(a['score_diff'], [-1, 1])
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
    df['ball_bin'] = np.digitize(df['ball_y'], BALL_EDGES[1:-1])
    df['dose_500uu'] = np.floor(df['last_man_y_own']/500).astype(int)*500
    df['population'] = np.where(df['remaining'] <= 60,
                                np.where(df['score_diff'] == -1, 'late_trailing', 'late_leading'),
                                np.where(df['score_diff'] == -1, 'early_trailing', 'early_leading'))
    for key, values in event_labels(t[ii], int(meta['focal_team']), goals, replay).items():
        df[key] = values
    return df, {'grid_anchors': initial, 'eligible_anchors': len(df),
                'score_mismatch_anchors': score_mismatch,
                'unknown_demolition_state_anchors': int(np.isnan(a['players'][ii, :, 7]).any(axis=1).sum()),
                'missing_y15': int(df['y15'].isna().sum())}


def build_anchors(pairs, goals, replays, artifacts, seed=42, smoke=False, spacing=1., scratch=None):
    by_replay = replays.set_index('replay_id').to_dict('index')
    goal_groups = {rid: rows for rid, rows in goals.groupby('replay_id')}
    by_shard = defaultdict(list)
    for pair in pairs:
        for meta in pair:
            by_shard[meta['_shard']].append(meta)
    chunks, counts = [], Counter()
    for shard, records in sorted(by_shard.items()):
        with tempfile.TemporaryDirectory(prefix='p4-arrays-', dir=scratch or artifacts) as scratch_dir:
            arrays = None
            if not smoke:
                directory = Path(unpack_shard(shard, Path(scratch_dir)))
                arrays = {k: np.load(directory/(k+'.npy'), mmap_mode='r') for k in REQUIRED}
            for meta in records:
                # This guard is before read_slice/mmap, in addition to inventory.
                if meta['season'] not in ALLOWED_SEASONS or meta['split'] not in ('train', 'val'):
                    raise ValueError('Forbidden split before compact read')
                a = read_slice(meta) if smoke else {
                    k: v[int(meta['start']):int(meta['stop'])] for k, v in arrays.items()}
                rid = meta['replay_id']
                replay = dict(by_replay[rid], replay_id=rid)
                gg = goal_groups.get(rid, goals.iloc[:0])
                frame, diag = anchors_for_replay(meta, a, gg, replay, seed, spacing)
                if len(frame):
                    chunks.append(frame)
                counts.update(diag)
            del arrays
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


def feature_matrix(df, train_mask):
    regions = sorted(set(df.loc[train_mask, 'region']))
    names = list(NUMERIC_FEATURES) + [f'region={region}' for region in regions]
    x = np.column_stack([df[NUMERIC_FEATURES].to_numpy(dtype=np.float32)] +
                        [(df['region'] == region).to_numpy(dtype=np.float32) for region in regions])
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


def nuisance_predictions(df, folds=3, seed=42, iterations=80):
    train_mask = (df['split'] == 'train').to_numpy()
    train = np.flatnonzero(train_mask)
    val = np.flatnonzero(~train_mask)
    x, feature_names, regions = feature_matrix(df, train_mask)
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
    if folds >= 2:
        assignment = {s: i % folds for i, s in enumerate(series)}
        row_fold = df['series_id'].map(assignment).fillna(-1).to_numpy(int)
        manifest['series_fold_assignment'] = assignment
        for fold in range(folds):
            heldout = np.flatnonzero(train_mask & (row_fold == fold))
            fit = np.flatnonzero(train_mask & (row_fold != fold))
            assert not set(df.iloc[fit]['series_id']) & set(df.iloc[heldout]['series_id'])
            pp, diag = fit_predict(fit, heldout, x, a, df, seed+fold*100, iterations)
            pred[heldout] = pp
            manifest['fits'].append(dict(diag, fold=fold, target='train_oof'))
    else:
        manifest['train_oof_failure'] = 'fewer than two training series'
    if len(val):
        assert not set(df.iloc[train]['series_id']) & set(df.iloc[val]['series_id'])
        pp, diag = fit_predict(train, val, x, a, df, seed+10000, iterations)
        pred[val] = pp
        manifest['fits'].append(dict(diag, target='val'))
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
           'interpretation': 'RR sensitivity descriptor only; cannot cure structural positivity failure'}
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
            'balanced_below_0_1': bool(values and max(values) < .1)}


def estimate_contrast(df, pred, x, feature_names, label, trim, repeats, seed):
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
              'causal_identification': False, 'structural_positivity': False,
              'estimand': 'exploratory model-dependent numerical DR contrast in retained states; no identified intervention or standardized causal association',
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
    result['feasibility_gates'] = {'at_least_50_series': result['series'] >= 50,
                                   'at_least_20_series_each_arm': min(result['arm_series'].values()) >= 20,
                                   'at_least_50_unique_goals_each_arm_outcome': bool(unique) and min(unique.values()) >= 50,
                                   'smd_below_0_1': result['balance'].get('balanced_below_0_1', False),
                                   'structural_positivity': False}
    result['status'] = 'computed_association_causal_gate_failed'
    if label == 'ypast10':
        result['negative_control'] = {'events': int(np.count_nonzero(y)), 'degenerate': bool(np.count_nonzero(y) == 0),
                                      'caution': 'Behavior may respond to past goals; absence of signal does not validate exchangeability'}
    if label != 'ypast10':
        horizon = int(label[1:])
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


def analyze(df, pred, x, nuisance, repeats, seed):
    all_results = {}
    for split in ('train', 'val'):
        sm = (df['split'] == split).to_numpy()
        for population in ('late_trailing', 'late_leading', 'early_trailing', 'early_leading'):
            mask = sm & (df['population'] == population).to_numpy()
            sub = df.loc[mask].reset_index(drop=True)
            if not len(sub):
                all_results[f'{split}/{population}'] = {'status': 'no_anchors'}
                continue
            block = {'predictive': predictive_diagnostics(sub, pred[mask]), 'contrasts': {}}
            for label in ('y10', 'y5', 'y15', 'ypast10'):
                for trim in (0., .05, .1):
                    key = f'{label}/trim_{trim:.2f}'
                    block['contrasts'][key] = estimate_contrast(
                        sub, pred[mask], x[mask], nuisance['feature_names'], label, trim, repeats,
                        seed+stable_hash(f'{split}:{population}:{label}') % 100000)
            all_results[f'{split}/{population}'] = block
    return all_results


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
    print(json.dumps({'self_test': 'passed', 'checks': ['first-goal endpoints', 'competing identities',
                     'terminal and gap censoring', 'regulation end not censoring', 'series grid',
                     'equal-series bootstrap', 'RR E-value', 'train-only thresholds/regions',
                     'validation fit rejected', '2026/test path guards']}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
                                         smoke=args.max_replays is not None, spacing=args.anchor_spacing, scratch=args.scratch)
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
               'analysis': 'P4 C2 state-risk association plus requested numerical DR diagnostics; C3 initiation not identified',
               'causal_effect_identified': False,
               'structural_positivity_failure': 'Treatment is a deterministic function of included own player y and ball y. Approximate fitted overlap cannot restore positivity.',
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
                               'population': 'regulation, exact score +/-1, 10-180 seconds remaining'},
               'outcomes': '(t,t+T] first focal/opponent goal, T=5/10/15; certified game end absorbing; regulation end does not censor; unknown truncation missing; live/reset boundaries do not censor goals',
               'bootstrap': {'repeats': args.bootstrap, 'unit': 'whole series',
                              'weighting': 'within-series mean then equal-series mean',
                              'nuisances': 'fixed OOF or external predictions; cluster resampling of influence contributions; no nuisance refit; conditional on training data and frozen thresholds'},
               'multiplicity': 'Exploratory 2025 development. No confirmatory p-values or promotion to P4 C3; 5/15s, strata and dose are sensitivities.',
               'timing_seconds': {'events': events_seconds, 'anchors': anchor_seconds}}
    metrics = {'replays': len(ids), 'validated_replays': int(replays['validated'].sum()),
               'anchors': len(anchors), 'causal_identification_gate_passed': 0.}
    if len(anchors):
        anchors, thresholds = freeze_thresholds(anchors)
        details['thresholds'] = thresholds
        anchors.to_parquet(artifacts/'anchors.parquet', index=False)
        extremes = anchors[anchors['treatment'].notna()].reset_index(drop=True)
        details['dose_curve_val'] = dose_curve(anchors[anchors['split'] == 'val'], args.bootstrap, args.seed)
        if len(extremes) and (extremes['split'] == 'train').any():
            clock = time.perf_counter()
            pred, x, nuisance = nuisance_predictions(extremes, args.folds, args.seed, args.iterations)
            details['timing_seconds']['nuisances'] = time.perf_counter()-clock
            details['nuisances'] = nuisance
            np.savez_compressed(artifacts/'nuisance_predictions.npz', predictions=pred)
            extremes[['replay_id', 'series_id', 'focal_team', 'anchor_time', 'split', 'population', 'treatment']].to_parquet(
                artifacts/'prediction_rows.parquet', index=False)
            clock = time.perf_counter()
            details['estimates'] = analyze(extremes, pred, x, nuisance, args.bootstrap, args.seed)
            details['timing_seconds']['inference'] = time.perf_counter()-clock
            main_result = details['estimates'].get('val/late_trailing', {}).get('contrasts', {}).get('y10/trim_0.05', {})
            for key in ('difference_for', 'difference_against', 'difference_net_gd'):
                value = main_result.get('adjusted', {}).get(key, {}).get('estimate')
                if value is not None and np.isfinite(value):
                    metrics['exploratory_dr_'+key] = value
            details['status'] = main_result.get('status', 'insufficient_primary_validation_support')
        else:
            details['status'] = 'insufficient_training_extreme_support'
    else:
        details['status'] = 'no_eligible_anchors'
    details['timing_seconds']['total'] = time.perf_counter()-started
    result = {'method': 'train-frozen HGB / series-cross-fitted AIPW state-contrast audit',
              'task': 'pushup_dr', 'split': 'val', 'is_baseline': False,
              'metrics': metrics, 'details': details, 'updated': now(),
              'notes': ('FEASIBILITY SMOKE ONLY: bounded replay sample, no research conclusion or identified causal effect.'
                        if args.max_replays is not None else
                        'Exploratory development model-dependent contrasts; structural positivity fails for depth treatment with full geometry controls.')}
    atomic_json(guard_path(args.out), result)
    atomic_json(artifacts/'pushup_dr.json', result)
    print(json.dumps({'status': details['status'], 'metrics': metrics,
                      'timing_seconds': details['timing_seconds'], 'output': str(args.out)}))
    return result


if __name__ == '__main__':
    main()
