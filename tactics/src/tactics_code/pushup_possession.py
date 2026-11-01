"""P4 possession sensitivity, fixed by docs/P4_possession_prereg.md at d64a77d.

Only validation 2025, initiation primary arms, y10, trim .05, 3 grouped folds,
and 2,000 whole-series draws. Shared initiation/event/data code is unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import numpy as np
import pandas as pd

from . import pushup_dr as dr

PREREG_COMMIT = 'd64a77d'
FOLDS, ITERATIONS, BOOTSTRAP, SEED = 3, 80, 2000, 42
TRIM = .05
TOUCH_LEVELS = ('own', 'opponent', 'none')


def possession_features(a, indices):
    """Compact touch proxy in (t-5,t]; every selected array index is <= t.

    extract.py already rotates both ball coordinates/velocities to focal +y,
    and remaps touch player slots to own 0:3 / opponent 3:6. Its compact touch
    is a conservative candidate contact, not certified possession.
    """
    t = np.asarray(a['time'], float)
    ii = np.asarray(indices, int)
    if np.any(ii < 0) or np.any(ii >= len(t)) or np.any(np.diff(t) <= 0):
        raise ValueError('Invalid baseline indices/time')
    touch = np.asarray(a['touch'])
    if touch.shape != t.shape or not np.isin(touch, [-1, 0, 1, 2, 3, 4, 5]).all():
        raise ValueError('Expected canonical compact touch slots -1 or 0..5')
    # Cumulative past index, never nearest-event lookup or backward filling.
    last = np.maximum.accumulate(np.where(touch >= 0, np.arange(len(t)), -1))[ii]
    recent = (last >= 0) & (t[np.maximum(last, 0)] > t[ii]-5.)
    team = np.full(len(ii), 'none', dtype=object)
    team[recent] = np.where(touch[last[recent]] < 3, 'own', 'opponent')
    vy = np.asarray(a['ball'])[ii, 4]
    half = np.asarray(a['ball'])[ii, 1] > 0
    if not np.isfinite(np.asarray(a['ball'])[ii][:, [1, 4]]).all():
        raise ValueError('Nonfinite possession baseline ball state')
    strata = np.where((team == 'own') & (vy > 0), 'S_own',
                      np.where(team == 'opponent', 'S_opp', 'S_other'))
    return pd.DataFrame({'last_touch_team': team, 'ball_vy_attack': vy,
                         'ball_in_opp_half': half, 'possession_stratum': strata})


def read_touch_slice(meta):
    """Add only touch to the existing bounded smoke reader's required arrays."""
    with zipfile.ZipFile(dr.guard_path(meta['_shard'])) as archive:
        with archive.open('touch.npy') as stream:
            version = np.lib.format.read_magic(stream)
            reader = (np.lib.format.read_array_header_1_0 if version == (1, 0)
                      else np.lib.format.read_array_header_2_0)
            shape, fortran, dtype = reader(stream)
            if len(shape) != 1 or fortran or dtype.hasobject:
                raise ValueError('Unsupported compact touch layout')
            start, stop = int(meta['start']), int(meta['stop'])
            stream.seek(stream.tell()+start*dtype.itemsize)
            return np.frombuffer(stream.read((stop-start)*dtype.itemsize), dtype=dtype)


def anchor_shard(shard, records, goals, by_replay, artifacts, smoke, scratch):
    chunks, counts = [], Counter()
    with tempfile.TemporaryDirectory(prefix='p4-possession-', dir=scratch or artifacts) as work:
        arrays = None
        if not smoke:
            directory = Path(dr.unpack_shard(dr.guard_path(shard), Path(work)))
            with zipfile.ZipFile(dr.guard_path(shard)) as archive:
                with archive.open('touch.npy') as source, (directory/'touch.npy').open('wb') as target:
                    shutil.copyfileobj(source, target, 1024*1024)
            arrays = {k: np.load(directory/(k+'.npy'), mmap_mode='r', allow_pickle=False)
                      for k in dr.REQUIRED | {'touch'}}
        for meta in records:
            if meta['season'] not in dr.ALLOWED_SEASONS or meta['split'] not in ('train', 'val'):
                raise ValueError('Forbidden season/split before compact read')
            if smoke:
                a = dr.read_slice(meta)
                a['touch'] = read_touch_slice(meta)
            else:
                a = {k: v[int(meta['start']):int(meta['stop'])] for k, v in arrays.items()}
            rid = meta['replay_id']
            frame, audit = dr.anchors_for_replay(
                meta, a, goals[goals['replay_id'] == rid], dict(by_replay[rid], replay_id=rid),
                SEED, spacing=1., design='initiation')
            if len(frame):
                ii = np.searchsorted(a['time'], frame['state_time'].to_numpy())
                if not np.array_equal(a['time'][ii], frame['state_time'].to_numpy()):
                    raise ValueError('Baseline state must be an exact compact timestamp')
                frame = pd.concat([frame.reset_index(drop=True), possession_features(a, ii)], axis=1)
                chunks.append(frame)
            counts.update(audit)
    return chunks, counts


def build_anchors(pairs, goals, replays, artifacts, smoke=False, scratch=None, workers=1):
    by_replay = replays.set_index('replay_id').to_dict('index')
    by_shard = defaultdict(list)
    for pair in pairs:
        for meta in pair:
            by_shard[meta['_shard']].append(meta)
    tasks = [(shard, records, goals[goals['replay_id'].isin({r['replay_id'] for r in records})],
              by_replay, artifacts, smoke, scratch) for shard, records in sorted(by_shard.items())]
    chunks, counts = [], Counter()
    for frames, audit in dr.parallel_tasks(anchor_shard, tasks, workers):
        chunks.extend(frames)
        counts.update(audit)
    return (pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()), dict(counts)


def freeze_velocity_tertiles(df):
    """TRAIN-only equal-series tertiles; never replace the registered >0 rule.

    The prereg mentions train tertiles for P2 but explicitly defines S_own with
    velocity >0. Freeze the descriptive cutpoints; no additional tertile-stratum
    estimands are introduced. The model retains the continuous velocity.
    """
    train = df[df['split'] == 'train']
    cuts = None
    if len(train):
        xx = train['ball_vy_attack'].to_numpy(float)
        ww = dr.series_weights(train['series_id'])
        order = np.argsort(xx, kind='stable')
        cuts = np.interp([1/3, 2/3], (np.cumsum(ww[order])-.5*ww[order])/ww.sum(), xx[order])
    return {'fit_split': 'train', 'fit_seasons': list(dr.TRAIN_SEASONS),
            'weighting': 'equal series among baseline candidate anchors', 'cutpoints': cuts,
            'rows': len(train), 'series': int(train['series_id'].nunique()),
            'use': 'Frozen P2 descriptors only; continuous nuisance covariate; exact S_own uses >0.'}


def feature_matrix(df, train_mask):
    x, names, regions = dr.feature_matrix(df, train_mask, design='initiation')
    if not df['last_touch_team'].isin(TOUCH_LEVELS).all():
        raise ValueError('Unknown last_touch_team level')
    extra = np.column_stack([(df['last_touch_team'] == level).to_numpy(np.float32)
                             for level in TOUCH_LEVELS] +
                            [df['ball_vy_attack'].to_numpy(np.float32),
                             df['ball_in_opp_half'].to_numpy(np.float32)])
    if not np.isfinite(extra).all():
        raise ValueError('Nonfinite possession covariates')
    return np.column_stack([x, extra]), names + [f'last_touch_team={s}' for s in TOUCH_LEVELS] + [
        'ball_vy_attack', 'ball_in_opp_half'], regions


def nuisance_predictions(df, workers=1, lowmem=False):
    """Same series-fold scheduler as dr; reuse its fitter without extra outcomes.

    dr.nuisance_predictions hardcodes its feature factory and four outcomes.
    This thin scheduler adds P1-P3 without mutating that module's globals. Empty
    unused labels make dr.fit_predict skip those fits; its 25-column ABI remains.
    """
    if not df['split'].isin(['train', 'val']).all():
        raise ValueError('Only train/val nuisance rows allowed')
    train_mask = df['split'].eq('train').to_numpy()
    train, val = np.flatnonzero(train_mask), np.flatnonzero(~train_mask)
    if lowmem:
        from .lowmem import possession_feature_matrix
        x, names, regions = possession_feature_matrix(df, train_mask)
        print(json.dumps({'phase': 'p4_features', 'rows': len(df), 'columns': x.shape[1],
                          'x_bytes': x.nbytes, 'fit_workers': 1, 'fit_threads': 1}),
              file=sys.stderr, flush=True)
    else:
        x, names, regions = feature_matrix(df, train_mask)
    a = df['treatment'].to_numpy(int)
    fit_frame = df[['split', 'series_id', 'y10']].copy() if lowmem else df.copy()
    for label in ('y5', 'y15', 'ypast10'):
        fit_frame[label] = np.nan
    series = sorted(df.iloc[train]['series_id'].unique(), key=lambda s: dr.stable_hash(f'{SEED}:{s}:fold'))
    assignment = {s: i % FOLDS for i, s in enumerate(series)}
    manifest = {'scheme': '3 series-grouped TRAIN OOF folds; all-TRAIN frozen fit predicts 2025',
                'folds': FOLDS, 'series_fold_assignment': assignment, 'feature_names': names,
                'training_region_levels': regions, 'train_seasons': list(dr.TRAIN_SEASONS),
                'val_season': dr.VAL_SEASON, 'validation_rows_used_in_fit': 0,
                'algorithm': 'pushup_dr.fit_predict / HistGradientBoostingClassifier',
                'max_iter': ITERATIONS, 'fitted_outcomes': ['y10'], 'fits': [],
                'unknown_validation_last_man_id_rows': int((~df.loc[~train_mask, 'last_man_id'].isin(
                    set(df.loc[train_mask, 'last_man_id']))).sum())}
    pred = np.full((len(df), 25), np.nan)
    if len(series) < FOLDS:
        manifest['failure'] = 'Fewer than three TRAIN series; preregistered folds not reduced'
        return pred, x, manifest
    if set(df.iloc[train]['series_id']) & set(df.iloc[val]['series_id']):
        raise ValueError('Series crosses train/validation')
    row_fold = df['series_id'].map(assignment).fillna(-1).to_numpy(int)
    tasks, destinations = [], []
    for fold in range(FOLDS):
        heldout = np.flatnonzero(train_mask & (row_fold == fold))
        fit = np.flatnonzero(train_mask & (row_fold != fold))
        tasks.append((fit, heldout, x, a, fit_frame, SEED+fold*100, ITERATIONS))
        destinations.append((heldout, {'fold': fold, 'target': 'train_oof'}))
    if len(val):
        tasks.append((train, val, x, a, fit_frame, SEED+10000, ITERATIONS))
        destinations.append((val, {'target': 'val'}))
    for (pp, diag), (indices, context) in zip(dr.parallel_tasks(
            dr.fit_predict, tasks, 1 if lowmem else min(workers, len(tasks)),
            1 if lowmem else max(1, workers//len(tasks))), destinations):
        pred[indices] = pp
        manifest['fits'].append(dict(diag, **context))
    return pred, x, manifest


def estimate_contrast(df, pred, x, names):
    result = dr.estimate_contrast(df, pred, x, names, 'y10', TRIM, BOOTSTRAP, SEED, 'initiation')
    arms = result.get('balance', {}).get('arms', {})
    min_ess = min((arms.get(str(a), {}).get('series_weight_ess', 0.) for a in (0, 1)))
    result['minimum_arm_series_ess'] = min_ess
    result['estimable'] = bool(min_ess >= dr.OVERLAP_GATES['minimum_series_ess'] and 'adjusted' in result)
    result['bootstrap_repeats'] = BOOTSTRAP
    if not result['estimable']:
        result['status'] = 'not_estimable'
        result['interpretation'] = 'No interpretation: missing arm/support or series ESS <20; numerical audit only.'
        result['causal_identification'] = False
    return result


def series_net_contributions(df, pred):
    """Exact y10 AIPW equation from dr.estimate_contrast, for paired R5 only."""
    y, a, e = df['y10'].to_numpy(float), df['treatment'].to_numpy(int), pred[:, 0]
    m = pred[:, 7:13].reshape(-1, 2, 3)
    keep = np.isfinite(y) & np.isfinite(e) & np.isfinite(m).all(axis=(1, 2)) & (e >= TRIM) & (e <= 1-TRIM)
    y, a, e, m = y[keep], a[keep], np.clip(e[keep], 1e-6, 1-1e-6), m[keep]
    actual = np.column_stack([y == 1, y == 2]).astype(float)
    psi = [m[:, arm, 1:3] + ((a == arm)/(e if arm else 1-e))[:, None]*(actual-m[:, arm, 1:3])
           for arm in (0, 1)]
    value = (psi[1][:, 0]-psi[1][:, 1])-(psi[0][:, 0]-psi[0][:, 1])
    return pd.Series(value, index=df.loc[keep, 'series_id'].to_numpy(), dtype=float).groupby(level=0).mean()


def paired_urgency(late, tied):
    """Resample the union of series once per draw, preserving missing membership."""
    table = pd.concat([late.rename('late'), tied.rename('tied')], axis=1).sort_index()
    result = {'bootstrap_repeats': BOOTSTRAP, 'unit': 'paired whole series, union of retained series',
              'late_series': len(late), 'tied_series': len(tied),
              'shared_series': len(late.index.intersection(tied.index)), 'union_series': len(table),
              'estimate': None, 'ci95': None, 'invalid_bootstrap_replicates': BOOTSTRAP}
    if not len(late) or not len(tied):
        return result
    values = np.column_stack([table['late'].fillna(0), table['late'].notna(),
                              table['tied'].fillna(0), table['tied'].notna()])
    point, _, draws = dr.cluster_bootstrap(values, table.index, BOOTSTRAP, SEED)
    result['estimate'] = float(point[0]/point[1]-point[2]/point[3])
    valid = (draws[:, 1] > 0) & (draws[:, 3] > 0)
    result['invalid_bootstrap_replicates'] = int(BOOTSTRAP-valid.sum())
    if valid.all() and len(draws) == BOOTSTRAP:
        difference = draws[:, 0]/draws[:, 1]-draws[:, 2]/draws[:, 3]
        result['ci95'] = np.quantile(difference, [.025, .975])
    return result


def _effect(result, key):
    return result.get('adjusted', {}).get(key, {'estimate': None, 'ci95': None})


def _finite_ci(effect):
    ci = effect.get('ci95')
    return ci is not None and len(ci) == 2 and bool(np.isfinite(ci).all())


def evaluate_rules(estimates, urgency, smoke=False):
    full, opp = estimates['full_model'], estimates['S_opp']
    net, oppnet = _effect(full, 'difference_net_gd'), _effect(opp, 'difference_net_gd')
    concede = _effect(opp, 'difference_against')
    def eligible(r):
        return bool(r.get('estimable', False) and not smoke)
    def negative(r, effect):
        return bool(eligible(r) and _finite_ci(effect) and effect['estimate'] < 0 and effect['ci95'][1] < 0)
    r1 = bool(eligible(full) and _finite_ci(net) and net['ci95'][0] <= 0 <= net['ci95'][1]
              and abs(net['estimate']) <= .5*.088)
    r3 = bool(eligible(opp) and concede['estimate'] is not None and np.isfinite(concede['estimate'])
              and concede['estimate'] >= 0)
    diagnostics = {}
    for name, result in estimates.items():
        diagnostics[name] = {'max_abs_smd': result.get('balance', {}).get('max_abs_smd_after'),
                             'ess_by_arm': result.get('balance', {}).get('arms', {}),
                             'minimum_arm_series_ess': result['minimum_arm_series_ess'],
                             'trim_fraction': result.get('trim_fraction'), 'estimable': result['estimable'],
                             'status': result['status'], 'causal_gate_passed': result['causal_identification']}
    r5 = bool(eligible(full) and eligible(estimates['tied_full_model']) and _finite_ci(urgency)
              and (urgency['ci95'][0] > 0 or urgency['ci95'][1] < 0))
    conditions = {
        'R1': (dict(full_model=net, reference_unconditioned_net_gd=.088, maximum_absolute_estimate=.044,
                    estimable=full['estimable']), r1),
        'R2': (dict(full_model=net, S_opp=oppnet, full_estimable=full['estimable'], S_opp_estimable=opp['estimable']),
               negative(full, net) or negative(opp, oppnet)),
        'R3': (dict(S_opp_concede=concede, estimable=opp['estimable']), r3),
        'R4': (dict(minimum_series_ess=20, analyses=diagnostics), all(r['estimable'] for r in estimates.values())),
        'R5': (dict(paired_urgency=urgency, late_estimable=full['estimable'],
                    tied_estimable=estimates['tied_full_model']['estimable']), r5)}
    return {name: {'inputs': inputs, 'pass': bool(passed), 'status': 'pass' if passed else 'fail',
                   'smoke_only': smoke} for name, (inputs, passed) in conditions.items()}


def analyze(df, pred, x, names):
    masks = {'full_model': df['population'].eq('late_trailing').to_numpy(),
             'S_own': (df['population'].eq('late_trailing') & df['possession_stratum'].eq('S_own')).to_numpy(),
             'S_opp': (df['population'].eq('late_trailing') & df['possession_stratum'].eq('S_opp')).to_numpy(),
             'tied_full_model': df['population'].eq('tied').to_numpy()}
    estimates, contributions = {}, {}
    for name, mask in masks.items():
        mask = mask & df['split'].eq('val').to_numpy()
        sub = df.loc[mask].reset_index(drop=True)
        estimates[name] = estimate_contrast(sub, pred[mask], x[mask], names)
        if name in ('full_model', 'tied_full_model'):
            contributions[name] = series_net_contributions(sub, pred[mask])
            if 'adjusted' in estimates[name]:
                np.testing.assert_allclose(contributions[name].mean(),
                    estimates[name]['adjusted']['difference_net_gd']['estimate'], rtol=1e-12, atol=1e-12)
    return estimates, paired_urgency(contributions['full_model'], contributions['tied_full_model'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--out', type=Path, default=Path('results/pushup_possession.json'))
    parser.add_argument('--data-root', type=Path, default=dr.DEFAULT_DATA_ROOT)
    parser.add_argument('--state-map', type=Path, default=Path('state_map_rlcs.json'))
    parser.add_argument('--max-replays', type=int)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--lowmem', action='store_true',
                        help='Same estimator; allocate features once and run nuisance fits serially')
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error('workers must be positive')
    if args.max_replays is not None and (not 1 <= args.max_replays <= 40 or args.workers != 1):
        parser.error('Bounded smoke requires 1..40 replays and one worker')
    started = time.perf_counter()
    compact = dr.guard_path(args.compact or (dr.MEDIUM if dr.MEDIUM.exists() else dr.SMALL))
    artifacts, output = dr.guard_path(args.artifacts), dr.guard_path(args.out)
    for destination in (artifacts, output, args.scratch):
        if destination is not None:
            destination = dr.guard_path(destination).resolve()
            if destination == compact.resolve() or compact.resolve() in destination.parents:
                raise ValueError('Outputs must not modify input compact')
    artifacts.mkdir(parents=True, exist_ok=True)
    if args.scratch:
        dr.guard_path(args.scratch).mkdir(parents=True, exist_ok=True)
    pairs, inventory = dr.metadata_inventory(compact)
    pairs = dr.select_pairs(pairs, args.max_replays, seed=SEED)
    if not pairs:
        raise ValueError('No allowed replays selected')
    selected = [row for pair in pairs for row in pair]
    ids = sorted({row['replay_id'] for row in selected})
    dr.atomic_json(artifacts/'selected_replays.json', ids)
    timing = {'inventory': time.perf_counter()-started}
    clock = time.perf_counter()
    print('phase=events start', file=sys.stderr, flush=True)
    goals, replays = dr.build_events(selected, artifacts, data_root=dr.guard_path(args.data_root),
                                     state_map_path=dr.guard_path(args.state_map))
    timing['events'] = time.perf_counter()-clock
    clock = time.perf_counter()
    print('phase=anchors start', file=sys.stderr, flush=True)
    anchors, audit = build_anchors(pairs, goals, replays, artifacts, args.max_replays is not None,
                                   args.scratch, args.workers)
    timing['anchors'] = time.perf_counter()-clock
    if anchors.empty:
        raise ValueError('No eligible anchors; no analysis result written')
    velocity_tertiles = freeze_velocity_tertiles(anchors)
    assigned, thresholds = dr.freeze_initiation(anchors, delta=500., control='third', include_early=False)
    if args.lowmem:
        del anchors
    assigned.to_parquet(artifacts/'anchors.parquet', index=False)
    extremes = assigned[assigned['treatment'].notna()].reset_index(drop=True)
    if args.lowmem:
        del assigned
    if extremes.empty:
        raise ValueError('No observed primary treatment arms')
    clock = time.perf_counter()
    print('phase=nuisances start', file=sys.stderr, flush=True)
    pred, x, nuisance = nuisance_predictions(extremes, args.workers, args.lowmem)
    timing['nuisances'] = time.perf_counter()-clock
    np.savez_compressed(artifacts/'nuisance_predictions.npz', predictions=pred)
    extremes[['replay_id', 'series_id', 'focal_team', 'anchor_time', 'split', 'population',
              'possession_stratum', 'treatment']].to_parquet(artifacts/'prediction_rows.parquet', index=False)
    clock = time.perf_counter()
    print('phase=inference start', file=sys.stderr, flush=True)
    estimates, urgency = analyze(extremes, pred, x, nuisance['feature_names'])
    timing['inference'] = time.perf_counter()-clock
    smoke = args.max_replays is not None
    rules = evaluate_rules(estimates, urgency, smoke)
    source = Path(__file__).parent
    hashes = {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in
              ('pushup_possession.py', 'pushup_dr.py', 'events.py', 'screen.py', 'data.py', 'extract.py', 'pressure.py')}
    if args.lowmem:
        hashes['lowmem.py'] = hashlib.sha256((source/'lowmem.py').read_bytes()).hexdigest()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    timing['total'] = time.perf_counter()-started
    result = {'task': 'pushup_possession', 'method': 'possession-conditioned train-frozen HGB / AIPW initiation',
              'split': 'val', 'is_baseline': False, 'updated': dr.now(), 'rules': rules,
              'details': {'preregistration_commit': PREREG_COMMIT, 'parameters': vars(args),
                          'source_provenance': {'git_head_at_run': head, 'source_sha256': hashes},
                          'smoke_sample': smoke, 'selected_replay_count': len(ids),
                          'test_2026_opened': False, 'allowed_seasons': list(dr.ALLOWED_SEASONS),
                          'inventory': inventory, 'anchor_audit': audit, 'thresholds': thresholds,
                          'velocity_train_tertiles': velocity_tertiles, 'nuisances': nuisance,
                          'estimates': estimates, 'urgency': urgency, 'timing_seconds': timing,
                          'outcome': 'First goal in (t+1,t+11]; primary one-second early-goal exclusion',
                          'overlap_gate_thresholds': dr.OVERLAP_GATES,
                          'bootstrap': {'repeats': BOOTSTRAP, 'unit': 'whole series',
                                        'weighting': 'equal series', 'nuisances': 'fixed TRAIN/OOF predictions'},
                          'causal_identification': bool(not smoke and estimates['full_model']['causal_identification']),
                          'causal_assumptions': 'No unmeasured confounding, consistency, noninformative landmark selection/measurement/censoring, independent series; overlap gates necessary, not proof.',
                          'possession_caution': 'Compact touch is a conservative candidate-contact proxy, not certified possession.',
                          'series_completeness': 'All available compact members in batch; bounded smoke may select partial series.'},
              'notes': ('FEASIBILITY SMOKE ONLY; no research claims.' if smoke else
                        'Preregistered development sensitivity; R4 nonestimable strata are not interpreted; causal language requires unchanged original gates and assumptions.')}
    dr.atomic_json(output, result)
    dr.atomic_json(artifacts/'pushup_possession.json', result)
    print(json.dumps({'output': str(output), 'replays': len(ids), 'timing_seconds': timing,
                      'rules': {key: value['status'] for key, value in rules.items()}}))
    return result


if __name__ == '__main__':
    main()
