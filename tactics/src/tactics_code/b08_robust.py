"""Preregistered B08 robustness. CPU Slurm only; explicit development allowlist."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import tempfile
import time

for _name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
              'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import numpy as np

from . import screen_v2 as v2
from .common import atomic_json, clean, now

old = v2.old
SEEDS = (42, 43, 44)
PAIRS = ((0, 1), (0, 2), (1, 2))
VARIANTS = ('main', 'quantile_10', 'quantile_20', 'quantile_30',
            'exclude_kickoff_3s', 'exclude_overtime',
            'reference_rlcs-21-22', 'reference_rlcs-22-23', 'reference_rlcs-2024',
            'leading', 'tied', 'trailing', 'own_half', 'opponent_half')


def digest(path):
    h = hashlib.sha256()
    with old.guard_path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def extract_game(task):
    pair, mmap_dir = task
    result = {seed: [] for seed in SEEDS}
    exclusions = Counter()
    boost_audit = {}
    for perspective, meta in enumerate(pair):
        if meta['season'] not in old.ALLOWED_SEASONS:
            raise ValueError('Forbidden season before array open')
        expected = 'train' if meta['season'] in old.TRAIN_SEASONS else 'val'
        if meta['split'] != expected:
            raise ValueError('Season/split mismatch before array open')
        start, stop = int(meta['start']), int(meta['stop'])
        arrays = {key: np.load(old.guard_path(Path(mmap_dir)/(key+'.npy')),
                              mmap_mode='r', allow_pickle=False)[start:stop]
                  for key in old.REQUIRED}
        c = old.Context(meta, arrays, SEEDS[0])
        live = arrays['live'].astype(bool)
        starts = np.flatnonzero(live & np.r_[True, (~live[:-1]) |
                                (np.diff(arrays['segment']) != 0)])
        restart_times = np.asarray(c.t[starts], float)
        if perspective == 0 and meta['split'] == 'train':
            boost = arrays['players'][:, :, 6]
            boost = boost[np.isfinite(boost)]
            if len(boost):
                top = float(boost.max())
                boost_audit = dict(min=float(boost.min()), max=top, n=len(boost),
                                  at_max=int(np.isclose(boost, top, atol=.001).sum()))
        for seed in SEEDS:
            c.seed = seed
            for row in old.B08(c):
                row['ball_half'] = 'own_half' if row['ball'][1] < 0 else 'opponent_half'
                row['kickoff_distance'] = (float(np.min(np.abs(restart_times-row['time'])))
                                           if len(restart_times) else float('inf'))
                slim = v2._v2_slim(row, 'B08', meta, c)
                if not np.isfinite(slim['controls']).all():
                    exclusions[f'{seed}:nonfinite_controls'] += 1
                    continue
                result[seed].append(slim)
    return dict(rows=result, boost_audit=boost_audit, exclusions=dict(exclusions))


def pair_products(values):
    return sum(values[:, i]*values[:, j] for i, j in PAIRS)/3.


def ratio_stat(rows, actual, expected, seed, label, reps, workers):
    if not rows:
        return v2._missing(rows, 'Empty preregistered cell')
    result = v2._cluster_stat(rows, np.column_stack([actual, expected]),
        lambda a: a[0]/a[1] if a[1] > 1e-8 else np.nan,
        label, seed, reps, workers)
    # _cluster_stat defaults to null=0. Do not present that p-value for a ratio.
    result.pop('p', None)
    result.setdefault('details', {}).pop('p_method', None)
    w = v2._weights(rows)
    result['observed_pair_risk'] = float(np.average(actual, weights=w))
    result['independent_pair_risk'] = float(np.average(expected, weights=w))
    result['pass'] = bool(result['status'] == 'computed' and result['effect'] < 1
                          and result['ci95'][1] is not None and result['ci95'][1] < 1)
    return result


def fit_predict(train, val, cutoff, seed):
    fitting = v2._cap_train(train, seed=seed)
    yy = np.asarray([r['future_boost'] for r in fitting]) < cutoff
    model = v2.FrozenRidge(fitting, yy)
    prob = np.clip(model.predict(val), .005, .995)
    return prob, len(fitting)


def admissible_offsets(times):
    """Every matched time is >=20 s apart in both circular directions."""
    times = np.asarray(times, float)
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        return np.empty(0, int), np.empty(0)
    period = times[-1]-times[0]+6.
    offsets, minimums = [], []
    for offset in range(1, len(times)):
        delta = np.mod(times-np.roll(times, offset), period)
        separation = float(np.minimum(delta, period-delta).min())
        if separation >= 20.-1e-7:
            offsets.append(offset)
            minimums.append(separation)
    return np.asarray(offsets, int), np.asarray(minimums, float)


def shifted_null(rows, observed, prob, seed, reps, workers):
    games = defaultdict(list)
    for index, row in enumerate(rows):
        games[(str(row['replay_id']), int(row['focal_team']))].append(index)
    selected, actual_parts, expected_parts, empirical_parts = [], [], [], []
    shifts, excluded = [], []
    for key, indices in sorted(games.items()):
        indices = np.asarray(sorted(indices, key=lambda i: rows[i]['time']), int)
        tt = np.asarray([rows[i]['time'] for i in indices])
        offsets, separations = admissible_offsets(tt)
        if not len(offsets):
            excluded.append(dict(replay_id=key[0], focal_team=key[1], n_rows=len(indices)))
            continue
        y, p = observed[indices], prob[indices]
        actual = np.zeros(len(indices))
        expected = np.zeros(len(indices))
        pair_shifts = []
        for pair_index, (i, j) in enumerate(PAIRS):
            rng = old.replicate_rng(seed, 'B08_circular', pair_index, repr(key))
            choice = int(rng.integers(len(offsets)))
            offset = int(offsets[choice])
            actual += y[:, i]*np.roll(y[:, j], offset)/3.
            expected += p[:, i]*np.roll(p[:, j], offset)/3.
            pair_shifts.append(dict(pair=[i, j], anchor_offset=offset,
                                    min_circular_seconds=float(separations[choice])))
        empirical = pair_products(y.mean(axis=0, keepdims=True))[0]
        selected.extend(indices.tolist())
        actual_parts.append(actual)
        expected_parts.append(expected)
        empirical_parts.append(np.full(len(indices), empirical))
        shifts.append(dict(replay_id=key[0], focal_team=key[1], n_rows=len(indices),
                           admissible_offsets=len(offsets), pairs=pair_shifts))
    kept = [rows[i] for i in selected]
    if not kept:
        return dict(primary=v2._missing([], 'No game admits a >=20 second shift'),
                    pass_null=False, excluded_games=excluded, shifts=shifts)
    actual, expected = np.concatenate(actual_parts), np.concatenate(expected_parts)
    primary = ratio_stat(kept, actual, expected, seed, 'B08_circular', reps, workers)
    empirical = ratio_stat(kept, actual, np.concatenate(empirical_parts), seed,
                           'B08_circular_empirical', reps, workers)
    unshifted = ratio_stat(kept, pair_products(observed[selected]), pair_products(prob[selected]),
                           seed, 'B08_circular_eligible_unshifted', reps, workers)
    ci = primary['ci95']
    passed = bool(primary['status'] == 'computed' and ci[0] is not None and ci[0] <= 1 <= ci[1])
    primary.pop('pass', None)
    return dict(primary=primary, pass_null=passed, empirical_marginal_diagnostic=empirical,
                eligible_unshifted_diagnostic=unshifted, shifts=shifts,
                excluded_games=excluded, eligible_game_perspectives=len(shifts),
                excluded_rows=sum(g['n_rows'] for g in excluded),
                min_circular_seconds=min(p['min_circular_seconds'] for g in shifts for p in g['pairs']))


def evaluate_seed(rows, scale, seed, reps, workers, log):
    train = [r for r in rows if r['split'] == 'train']
    val = [r for r in rows if r['split'] == 'val']
    future_train = np.asarray([r['future_boost'] for r in train])
    future_val = np.asarray([r['future_boost'] for r in val])
    quantiles = np.quantile(future_train.ravel(), [.1, .2, .3])
    main_cutoff = .2*scale
    main_prob, main_fit_n = fit_predict(train, val, main_cutoff, seed)
    variants = []
    for name in VARIANTS:
        started = time.perf_counter()
        cutoff, probability, fit_n, reference = main_cutoff, main_prob, main_fit_n, list(old.TRAIN_SEASONS)
        mask = np.ones(len(val), bool)
        if name.startswith('quantile_'):
            qindex = int(name.split('_')[1])//10-1
            cutoff = float(quantiles[qindex])
            probability, fit_n = fit_predict(train, val, cutoff, seed)
        elif name.startswith('reference_'):
            season = name[len('reference_'):]
            reference = [season]
            subset = [r for r in train if r['season'] == season]
            if not subset:
                missing = v2._missing(val, 'No training rows for registered reference season')
                variants.append(dict(name=name, seed=seed, pass_cell=False, **missing))
                continue
            probability, fit_n = fit_predict(subset, val, cutoff, seed)
        elif name == 'exclude_kickoff_3s':
            mask = np.asarray([r['kickoff_distance'] > 3.+1e-7 for r in val])
        elif name == 'exclude_overtime':
            mask = np.asarray([r['overtime'] == 0 for r in val])
        elif name in ('leading', 'tied', 'trailing'):
            sign = {'leading': 1, 'tied': 0, 'trailing': -1}[name]
            mask = np.asarray([np.sign(r['score_diff']) == sign for r in val])
        elif name in ('own_half', 'opponent_half'):
            mask = np.asarray([r['ball_half'] == name for r in val])
        selected = [r for r, keep in zip(val, mask) if keep]
        observed = (future_val[mask] < cutoff).astype(float)
        probability = probability[mask]
        # Main seed 42 uses the original B08 replicate stream for exact reproduction.
        label = 'B08' if name == 'main' else 'B08_'+name
        result = ratio_stat(selected, pair_products(observed), pair_products(probability),
                            seed, label, reps, workers)
        result['pass_cell'] = result.pop('pass', False)
        result.update(name=name, seed=seed, cutoff=cutoff, reference_seasons=reference,
                      train_fit_rows=fit_n, excluded_evaluation_rows=int((~mask).sum()),
                      seconds=time.perf_counter()-started)
        if selected:
            result['marginal_mean_error'] = np.average(observed-probability, axis=0,
                                                      weights=v2._weights(selected)).tolist()
        variants.append(result)
        log(stage='variant', seed=seed, name=name, ratio=result['effect'], ci95=result['ci95'])
    null = shifted_null(val, (future_val < main_cutoff).astype(float), main_prob,
                        seed, reps, workers)
    return dict(seed=seed, n_train=len(train), n_val=len(val),
                quantile_cutoffs=dict(zip(('10', '20', '30'), quantiles.tolist())),
                variants=variants, null=null)


def verdict(seed_results):
    cells = [v for r in seed_results for v in r['variants']]
    passed = sum(v['pass_cell'] for v in cells)
    family_pass = len(cells) == 42 and passed >= 34
    null_pass = len(seed_results) == 3 and all(r['null']['pass_null'] for r in seed_results)
    return dict(variant_passes=passed, variant_total=42, fraction=passed/42,
                minimum_passes=34, family_pass=family_pass, all_nulls_include_one=null_pass,
                overall='PASS' if family_pass and null_pass else 'FAIL',
                by_seed={str(r['seed']): sum(v['pass_cell'] for v in r['variants'])/14 for r in seed_results})


def self_test():
    # Pure synthetic: no replay or metadata reads.
    for forbidden in ('/tmp/rlcs-2026/x.npz', '/tmp/test/x.npz'):
        try:
            old.guard_path(forbidden)
        except ValueError:
            pass
        else:
            raise AssertionError('Forbidden split guard failed')
    times = np.arange(30)*6.
    offsets, minima = admissible_offsets(times)
    assert len(offsets) and np.all(minima >= 20)
    for offset in offsets:
        delta = np.mod(times-np.roll(times, offset), 180.)
        assert np.all(np.minimum(delta, 180.-delta) >= 20)
    assert not len(admissible_offsets(np.arange(6)*6.)[0])
    rng = np.random.default_rng(402)
    rows, y = [], []
    for game in range(180):
        for t in times:
            rows.append(dict(series_id=str(game//3), roster_id=str(game % 2),
                             replay_id=str(game), focal_team=0, time=float(t)))
            # Perfect simultaneous dependence is destroyed by shifting one member.
            low = float(rng.random() < .25)
            y.append([low]*3)
    y = np.asarray(y)
    p = np.full(y.shape, .25)
    a = shifted_null(rows, y, p, 42, 299, 1)
    b = shifted_null(rows, y, p, 42, 299, 1)
    assert a == b, 'Null must be seed deterministic'
    assert abs(a['primary']['effect']-1) < .2
    assert a['eligible_unshifted_diagnostic']['effect'] > 3
    assert a['min_circular_seconds'] >= 20
    # Exactly 34/42 succeeds; 33/42 or any failed null fails.
    examples = [dict(seed=s, variants=[dict(pass_cell=True)]*14,
                     null=dict(pass_null=True)) for s in SEEDS]
    for index in range(8):
        examples[0]['variants'][index] = dict(pass_cell=False)
    assert verdict(examples)['overall'] == 'PASS'
    examples[0]['variants'][8] = dict(pass_cell=False)
    assert verdict(examples)['overall'] == 'FAIL'
    examples[0]['variants'][8] = dict(pass_cell=True)
    examples[1]['null']['pass_null'] = False
    assert verdict(examples)['overall'] == 'FAIL'
    return dict(status='passed', null_ratio=a['primary']['effect'],
                planted_unshifted_ratio=a['eligible_unshifted_diagnostic']['effect'],
                min_shift_seconds=a['min_circular_seconds'])


def write_report(report, destination):
    decision = report['verdict']
    lines = ['# B08 robustness', '',
        f"**Verdict: {decision['overall']}** under the committed preregistration.", '',
        f"{decision['variant_passes']}/42 cells passed (required: at least 34/42); "
        f"all three null CIs include 1: {decision['all_nulls_include_one']}.", '',
        f"Preregistration commit: `{report['prereg_commit']}`. Job: `{report['job_id']}`. "
        f"Main raw boost cutoff: {report['main_cutoff']:g} (20% of scale {report['boost_scale']:g}).", '',
        'Training seasons: 21–22, 22–23, 2024. Evaluation: 2025 only. No 2026 data read.', '',
        'Each row changes one feature from the main specification. CIs are 95% whole-series '
        'bootstrap intervals, conditional on train-frozen marginal models; 2,000 replicates. '
        'Seeds change anchor phase, training subsampling, bootstrap and circular shifts. '
        'They are not independent replications. Passing requires ratio <1 and CI upper bound <1.', '',
        '| Variant | Seed | Cutoff | Rows | Series | Ratio | 95% CI | Pass |',
        '|---|---:|---:|---:|---:|---:|---|---|']
    def estimate(result):
        if result.get('effect') is None:
            return 'NA', 'NA'
        ci = result['ci95']
        return f"{result['effect']:.6f}", (f'[{ci[0]:.6f}, {ci[1]:.6f}]' if ci[0] is not None else 'NA')
    for seed_result in report['seeds']:
        for result in seed_result['variants']:
            point, ci = estimate(result)
            lines.append(f"| {result['name']} | {result['seed']} | {result.get('cutoff', float('nan')):.6g} | "
                         f"{result['n_events']} | {result['n_series']} | {point} | {ci} | "
                         f"{'PASS' if result['pass_cell'] else 'FAIL'} |")
    lines.extend(['', '## Circular-shift control', '',
        'For each pair, one teammate’s sampled boost and its matched model probabilities are '
        'circularly shifted within game by at least 20 seconds in both circular directions. '
        'The primary denominator remains the train-fitted independent prediction. '
        'Empirical-marginal and eligible-unshifted ratios are diagnostics only.', '',
        '| Seed | Primary null ratio | 95% CI | Includes 1 | Empirical null ratio (CI) | Eligible unshifted ratio (CI) |',
        '|---:|---:|---|---|---|---|'])
    for seed_result in report['seeds']:
        null = seed_result['null']
        point, ci = estimate(null['primary'])
        empirical, eci = estimate(null.get('empirical_marginal_diagnostic', {}))
        unshifted, uci = estimate(null.get('eligible_unshifted_diagnostic', {}))
        lines.append(f"| {seed_result['seed']} | {point} | {ci} | {null['pass_null']} | "
                     f'{empirical} {eci} | {unshifted} {uci} |')
    lines.extend(['', '## Audit and interpretation', '',
        f"Main seed-42 reproduction: `{json.dumps(report['reproduction'], sort_keys=True)}`.", '',
        'A failed shifted-model null is evidence against interpreting the screen ratio as '
        'robust coordination: held-out marginal miscalibration or persistent within-game '
        'structure can affect this ratio. A successful empirical-marginal diagnostic does '
        'not override a failed primary null. Live-segment starts conservatively proxy kickoff '
        'restarts, including other resets; the inherited anchor eligibility already removes '
        'the first three seconds after a segment start.', '',
        f"Elapsed analysis seconds: {report['elapsed_seconds']:.1f}. CPU workers: {report['workers']}. "
        'Walltime derivation: see the committed `slurm/b08_robust.sh` header.', '',
        'The JSON includes every cutoff, marginal prediction error, exclusion count, '
        'per-game shift and minimum separation, source/input hashes, and allowed data paths.', ''])
    with destination.open('x') as stream:
        stream.write('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=v2.DEFAULT_INPUT)
    parser.add_argument('--output', type=Path, default=Path('.'))
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True))
        return
    if not os.environ.get('SLURM_JOB_ID') or not 1 <= args.workers <= 16:
        parser.error('Requires CPU sbatch and 1--16 workers')
    if os.environ.get('SLURM_JOB_PARTITION') != 'amd-hdr100':
        parser.error('Requires amd-hdr100')
    if os.environ.get('SLURM_JOB_GPUS') or os.environ.get('SLURM_GPUS'):
        parser.error('CPU allocation only')
    prereg = args.output/'docs'/'B08_robustness_prereg.md'
    prereg_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', str(prereg.resolve())],
                                            cwd=args.output, text=True).strip()
    if not prereg_commit:
        parser.error('Preregistration must already be committed')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', str(prereg.resolve())],
                   cwd=args.output, check=True)
    result_path = args.output/'results'/'b08_robust.json'
    report_path = args.output/'docs'/'B08_robustness.md'
    if result_path.exists() or report_path.exists():
        parser.error('Refusing to overwrite existing output')
    started = time.perf_counter()
    def log(**values):
        print(json.dumps(clean(dict(elapsed_seconds=time.perf_counter()-started, **values))), flush=True)
    acceptance = self_test()
    groups, audit = old.metadata_inventory(args.input)
    input_paths = sorted({str(old.guard_path(r['_shard'])) for pair in groups for r in pair})
    # Hash only explicitly allowlisted inputs. No recursive discovery.
    hashes = {p: digest(p) for p in input_paths}
    for p in input_paths:
        hashes[str(Path(p).with_suffix('.parquet'))] = digest(Path(p).with_suffix('.parquet'))
    hashes[str(args.input/'extraction.json')] = digest(args.input/'extraction.json')
    log(stage='metadata', replays=len(groups), input_hashes=len(hashes))
    by_shard = defaultdict(list)
    for pair in groups:
        assert len({r['_shard'] for r in pair}) == 1
        by_shard[pair[0]['_shard']].append(pair)
    boost_audits, exclusions, seed_results = [], Counter(), []
    with tempfile.TemporaryDirectory(prefix='b08-robust-', dir=args.scratch) as temporary:
        temp = Path(temporary)
        streams = {s: (temp/f'{s}.pickle').open('wb') for s in SEEDS}
        completed = 0
        with ProcessPoolExecutor(max_workers=args.workers,
                                 mp_context=multiprocessing.get_context('fork')) as pool:
            for shard, pairs in sorted(by_shard.items()):
                directory = old.unpack_shard(Path(shard), temp)
                for item in pool.map(extract_game, ((pair, directory) for pair in pairs), chunksize=1):
                    for seed, rows in item['rows'].items():
                        pickle.dump(rows, streams[seed], protocol=5)
                    if item['boost_audit']:
                        boost_audits.append(item['boost_audit'])
                    exclusions.update(item['exclusions'])
                    completed += 1
                    if completed % 100 == 0:
                        log(stage='extraction', completed=completed)
                shutil.rmtree(directory)
        for stream in streams.values():
            stream.close()
        scale = max(r['max'] for r in boost_audits)
        saturation = sum(r['at_max'] for r in boost_audits if abs(r['max']-scale) < .001)/sum(r['n'] for r in boost_audits)
        if not scale > 0 or saturation < .001:
            raise ValueError('Original train boost-scale validation failed')
        for seed in SEEDS:
            rows = v2._load_measurements(temp/f'{seed}.pickle')
            seed_results.append(evaluate_seed(rows, scale, seed, 2000, args.workers, log))
            del rows
            log(stage='seed_complete', seed=seed)
    baseline_path = args.output/'results'/'screen_v2.json'
    baseline = json.loads(old.guard_path(baseline_path).read_text())
    # Recorded screen containers can be a list or dictionary; locate B08 without
    # assuming an unrelated screen metadata schema.
    def find_b08(node):
        if isinstance(node, dict):
            if isinstance(node.get('B08'), dict) and 'effect' in node['B08']:
                return node['B08']
            if node.get('id', node.get('idea')) == 'B08' and 'effect' in node:
                return node
            for value in node.values():
                found = find_b08(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = find_b08(value)
                if found is not None:
                    return found
        return None
    original = find_b08(baseline)
    main_result = seed_results[0]['variants'][0]
    reproduction = dict(reference_found=original is not None)
    if original is not None:
        reproduction.update(reference_effect=original['effect'], reference_ci95=original.get('ci95'),
                            difference=main_result['effect']-original['effect'],
                            within_1e_8=abs(main_result['effect']-original['effect']) < 1e-8)
    source_paths = [Path(__file__), Path(v2.__file__), Path(old.__file__), prereg,
                    args.output/'slurm'/'b08_robust.sh', baseline_path]
    report = dict(created_at=now(), prereg_commit=prereg_commit, job_id=os.environ['SLURM_JOB_ID'],
                  workers=args.workers, bootstrap_reps=2000, boost_scale=scale, main_cutoff=.2*scale,
                  boost_saturation_fraction=saturation, seeds=seed_results, verdict=verdict(seed_results),
                  reproduction=reproduction, self_test=acceptance, exclusions=dict(exclusions),
                  audit=audit, input_sha256=hashes, source_sha256={str(p): digest(p) for p in source_paths},
                  elapsed_seconds=time.perf_counter()-started)
    atomic_json(result_path, report)
    write_report(report, report_path)
    log(stage='complete', verdict=report['verdict'])


if __name__ == '__main__':
    main()
