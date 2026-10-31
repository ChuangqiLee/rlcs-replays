"""RQ4: handcrafted cross-season PLAYER retrieval; never open the 2026 split.

Run: python -m tactics_code.style_retrieval [--max-replays 30]
The fixed eligibility gate is >=20 distinct usable games in ONE train season
and >=20 in 2025, never pooled train counts. Smoke does not relax that gate.
Features are game means over valid live samples; series queries average games,
and player galleries average training games. Scaling/imputation use train only.
Euclidean distance is fixed, with no validation tuning or learned representation.

Primary gallery is global. Gallery identity labels are permuted within each
player's modal TRAIN region (ties lexical; international/unknown excluded from
region assignment), once per replicate across all queries. This preserves region
structure without fitting region strata from validation. Metrics average player-
series queries; percentile bootstrap resamples complete 2025 series, conditional
on the fitted gallery. P-values are one-sided Monte Carlo (1 + exceedances)/(B+1).

Control excludes candidates with a training roster equal to any query-series
roster, and other identities co-rostered with the query anywhere in development
metadata. The target must remain admissible, with >=2 candidates; excluded target
queries are reported, not scored as errors. Thus the control concerns roster
changers, not the whole population. Null permutations exchange embedding labels
within region while holding the identity-based candidate masks fixed; this avoids
spuriously treating disallowed shuffled targets as retrieval errors. Neither this
control nor identity retrieval establishes causal, context-independent style.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import zipfile

import numpy as np
import pandas as pd

from .data import iter_compact, parsed_json
from .screen import (ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, guard_path,
                     metadata_inventory, read_slice)

DEFAULT_COMPACT = Path('artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact')
EXTRA_ARRAYS = ('flags', 'roles', 'role_uncertain', 'touch')
MIN_GAMES = 20
REGIONS = {'EU': 'Europe', 'NA': 'North America', 'SAM': 'South America',
           'OCE': 'Oceania', 'MENA': 'Middle East & North Africa',
           'Middle East and North Africa': 'Middle East & North Africa',
           'APAC': 'Asia-Pacific', 'Asia Pacific': 'Asia-Pacific',
           'SSA': 'Sub-Saharan Africa'}


def check_rows(frame, split=None):
    if frame.empty:
        return
    expected = frame.season.map({**dict.fromkeys(TRAIN_SEASONS, 'train'), VAL_SEASON: 'val'})
    if expected.isna().any() or not expected.eq(frame.split).all():
        raise ValueError('Forbidden season/split (2026/test is never allowed)')
    if split and not frame.split.eq(split).all():
        raise ValueError(f'Expected only {split} rows')


def read_player_slice(meta):
    """Reuse the existing slice reader; extend only for action/role channels.

    ZIP seeking decompresses preceding bytes, but materializes only selected
    replay slices. No unrelated replay's array is interpreted or featurized.
    """
    check_rows(pd.DataFrame([meta]))
    arrays = read_slice(meta)
    start, stop = int(meta['start']), int(meta['stop'])
    with zipfile.ZipFile(guard_path(meta['_shard'])) as archive:
        for key in EXTRA_ARRAYS:
            with archive.open(key + '.npy') as stream:
                version = np.lib.format.read_magic(stream)
                reader = (np.lib.format.read_array_header_1_0 if version == (1, 0)
                          else np.lib.format.read_array_header_2_0)
                shape, fortran, dtype = reader(stream)
                if fortran or dtype.hasobject or not 0 <= start < stop <= shape[0]:
                    raise ValueError(f'Invalid {key} array layout/offset')
                width = math.prod(shape[1:])
                stream.seek(stream.tell() + start * width * dtype.itemsize)
                raw = stream.read((stop - start) * width * dtype.itemsize)
                arrays[key] = np.frombuffer(raw, dtype=dtype).reshape((stop-start,) + shape[1:])
    return arrays


def game_features(meta, arrays, min_seconds=10.):
    """Three own-team players only; no double counting opposing perspectives.

    Positions already face +y in compact data. Boost is raw 0..255; speed uu/s.
    Touches are conservative contact proxies, action rates are observed flag
    onsets. Differences/onsets never cross segment boundaries or missing tracks.
    """
    check_rows(pd.DataFrame([meta]))
    ids = parsed_json(meta.get('player_ids'), [])
    if len(ids) != 6 or any(not isinstance(p, str) or not p for p in ids) or len(set(ids)) != 6:
        raise ValueError('Six distinct stable player IDs required')
    a = arrays
    t = np.asarray(a['time'], float)
    segment = a['segment']
    p = a['players'][:, :3]
    fps = float(meta['fps'])
    dt = np.diff(t, prepend=np.nan)
    adjacent = ((dt > 0) & (dt <= 1.5 / fps) &
                (segment == np.roll(segment, 1)))
    adjacent[0] = False
    result = []
    for slot, identity in enumerate(ids[:3]):
        v = p[:, slot]
        valid = (a['live'].astype(bool) & (segment >= 0) & np.isfinite(t) &
                 np.isfinite(v[:, :7]).all(axis=1) & (v[:, 7] != 1))
        seconds = valid.sum() / fps
        if seconds < min_seconds:
            continue
        xyz = v[valid, :3]
        speed = np.linalg.norm(v[valid, 3:6], axis=1)
        boost = v[valid, 6] / 255.
        f = {}
        for xbin in range(3):
            for ybin in range(3):
                f[f'occupancy_{xbin}{ybin}'] = np.mean(
                    (np.digitize(xyz[:, 0], [-1365.33, 1365.33]) == xbin) &
                    (np.digitize(xyz[:, 1], [-1706.67, 1706.67]) == ybin))
        f.update(depth_mean=xyz[:, 1].mean()/5120., width_mean=np.abs(xyz[:, 0]).mean()/4096.,
                 height_mean=xyz[:, 2].mean()/2044., aerial_share=np.mean(xyz[:, 2] > 300),
                 speed_mean=speed.mean()/2300., speed_sd=speed.std()/2300.,
                 supersonic_share=np.mean(speed >= 2200), slow_share=np.mean(speed < 500),
                 boost_mean=boost.mean(), boost_empty_share=np.mean(boost <= .05),
                 boost_full_share=np.mean(boost >= .95))
        own_known = np.isfinite(p[:, :, :3]).all(axis=(1, 2)) & ~(p[:, :, 7] == 1).any(axis=1)
        depth = valid & own_known
        # Tied depth positions split credit instead of depending on slot ordering.
        ys = p[:, :, 1]
        for label, extremum in [('deepest', np.min), ('furthest', np.max)]:
            tied = ys == extremum(ys, axis=1)[:, None]
            credit = tied[:, slot] / np.maximum(tied.sum(axis=1), 1)
            f[label + '_share'] = credit[depth].mean() if depth.any() else np.nan
        roles = a['roles'][:, slot]
        role_valid = valid & ~a['role_uncertain'].astype(bool) & (roles >= 0)
        for rank in range(3):
            f[f'role_{rank}_share'] = np.mean(roles[role_valid] == rank) if role_valid.any() else np.nan
        ball_valid = valid & np.isfinite(a['ball'][:, :3]).all(axis=1)
        f['behind_ball_share'] = np.mean(v[ball_valid, 1] < a['ball'][ball_valid, 1]) if ball_valid.any() else np.nan
        pairs = valid & np.roll(valid, 1) & adjacent
        elapsed = dt[pairs].sum()
        spent = np.maximum(-np.diff(v[:, 6], prepend=np.nan), 0)/255.
        f['boost_spent_per_second'] = spent[pairs].sum()/elapsed if elapsed else np.nan
        f['touch_proxy_per_minute'] = 60*np.sum(a['touch'][valid] == slot)/seconds
        for j, name in enumerate(('dodge', 'jump', 'double_jump')):
            flag = a['flags'][:, slot, j]
            known = pairs & np.isfinite(flag) & np.isfinite(np.roll(flag, 1))
            onset = (flag > 0) & (np.roll(flag, 1) <= 0)
            exposure = dt[known].sum()
            f[name + '_per_minute'] = 60*np.sum(onset & known)/exposure if exposure else np.nan
        result.append({**{key: meta[key] for key in ('replay_id', 'series_id', 'season', 'split', 'roster_id')},
                       'region': REGIONS.get(meta.get('region'), meta.get('region')),
                       'identity_id': identity, 'live_seconds': seconds,
                       **{'f_' + key: float(value) for key, value in f.items()}})
    return result


def eligible_players(train, val):
    check_rows(train, 'train')
    check_rows(val, 'val')
    tc = train.groupby(['identity_id', 'season']).replay_id.nunique()
    train_ids = set(tc[tc >= MIN_GAMES].index.get_level_values(0))
    vc = val.groupby('identity_id').replay_id.nunique()
    return sorted(train_ids & set(vc[vc >= MIN_GAMES].index))


def fit_gallery(train, features):
    check_rows(train, 'train')
    # Collapse duplicate rows, preventing repeated perspective/segment weighting.
    games = train.groupby(['identity_id', 'season', 'replay_id'], sort=True)[features].mean().reset_index()
    x = games[features].to_numpy(float)
    finite = np.isfinite(x)
    count = finite.sum(axis=0)
    mean = np.divide(np.where(finite, x, 0).sum(axis=0), count,
                     out=np.zeros(len(features)), where=count > 0)
    imputed = np.where(finite, x, mean)
    scale = imputed.std(axis=0)
    scale[scale < 1e-10] = 1.
    games[features] = (imputed - mean)/scale
    gallery = games.groupby('identity_id', sort=True)[features].mean()
    return dict(ids=gallery.index.to_numpy(), vectors=gallery.to_numpy(), mean=mean, scale=scale,
                all_missing_features=[features[j] for j in np.flatnonzero(count == 0)])


def identity_regions(metadata):
    """One immutable exchangeability stratum per identity, from TRAIN only."""
    votes = defaultdict(Counter)
    for row in metadata:
        if row['split'] != 'train':
            continue
        region = REGIONS.get(row.get('region'), row.get('region'))
        if not region or region == 'international':
            continue
        for identity in parsed_json(row.get('player_ids'), [])[:3]:
            if identity:
                votes[identity][region] += 1
    return {identity: sorted(counts, key=lambda r: (-counts[r], r))[0]
            for identity, counts in votes.items()}


def context_maps(metadata):
    rosters, teammates = defaultdict(set), defaultdict(set)
    for row in metadata:
        ids = parsed_json(row.get('player_ids'), [])[:3]
        if len(ids) != 3 or not all(ids) or not row.get('roster_id'):
            raise ValueError('Known complete rosters required for team control')
        for identity in ids:
            teammates[identity].update(set(ids) - {identity})
            if row['split'] == 'train':
                rosters[identity].add(row['roster_id'])
    return rosters, teammates


def metric_scores(distances, target, allowed):
    """Fractional expected rank scores under uniform random distance tie order."""
    true_distance = distances[np.arange(len(target)), target]
    tied = np.isclose(distances, true_distance[:, None], rtol=1e-10, atol=1e-12) & allowed
    better = ((distances < true_distance[:, None]) & ~tied & allowed).sum(axis=1)
    ties = tied.sum(axis=1)
    if np.any(ties < 1):
        raise ValueError('Correct identity excluded from candidate set')
    harmonic = np.r_[0., np.cumsum(1/np.arange(1, distances.shape[1]+1))]
    return np.column_stack([np.clip(1-better, 0, ties)/ties,
                            np.clip(5-better, 0, ties)/ties,
                            (harmonic[better+ties] - harmonic[better])/ties])


def infer(distances, targets, masks, series, regions, permutations, bootstrap, seed):
    keep = masks[np.arange(len(targets)), targets] & (masks.sum(axis=1) >= 2)
    report = dict(queries_total=len(targets), queries_evaluated=int(keep.sum()),
                  excluded_true_identity=int((~masks[np.arange(len(targets)), targets]).sum()),
                  excluded_fewer_than_two_candidates=int((masks.sum(axis=1) < 2).sum()))
    if not keep.any():
        return dict(report, status='insufficient_data')
    d, target, allowed = distances[keep], targets[keep], masks[keep]
    score = metric_scores(d, target, allowed)
    point = score.mean(axis=0)
    sizes = allowed.sum(axis=1)
    harmonic = np.r_[0., np.cumsum(1/np.arange(1, distances.shape[1]+1))]
    chance = np.array([np.mean(1/sizes), np.mean(np.minimum(5, sizes)/sizes), np.mean(harmonic[sizes]/sizes)])
    rng = np.random.default_rng(seed)
    null = np.empty((permutations, 3))
    strata = [np.flatnonzero(regions == r) for r in sorted(set(regions))]
    for b in range(permutations):
        order = np.arange(len(regions))
        for indices in strata:
            order[indices] = rng.permutation(indices)
        # Shuffle identity labels on embeddings; roster-based masks stay fixed.
        null[b] = metric_scores(d[:, order], target, allowed).mean(axis=0)
    _, inverse = np.unique(np.asarray(series)[keep], return_inverse=True)
    n_series = inverse.max()+1
    sums = np.zeros((n_series, 3))
    np.add.at(sums, inverse, score)
    counts = np.bincount(inverse)
    rng = np.random.default_rng(seed + 1)
    draws = np.empty((bootstrap, 3))
    for b in range(bootstrap):
        weights = np.bincount(rng.integers(n_series, size=n_series), minlength=n_series)
        draws[b] = (weights @ sums)/(weights @ counts)
    details = {}
    for j, name in enumerate(('top1', 'top5', 'mrr')):
        interval = np.quantile(draws[:, j], [.025, .975]).tolist() if bootstrap else [None, None]
        details[name] = dict(estimate=float(point[j]), ci95=interval, chance=float(chance[j]),
                             null_mean=float(null[:, j].mean()) if permutations else None,
                             p_value=float((1 + np.sum(null[:, j] >= point[j]-1e-12))/(permutations+1)) if permutations else None)
    return dict(report, status='fit', metrics=details, n_series=int(n_series),
                candidate_count={'min': int(sizes.min()), 'median': float(np.median(sizes)), 'max': int(sizes.max())},
                permutations=permutations, bootstrap=bootstrap,
                null_stratum_sizes={r: int(np.sum(regions == r)) for r in sorted(set(regions))})


def evaluate_retrieval(train, val, features, metadata, permutations=2000, bootstrap=2000, seed=42):
    check_rows(train, 'train')
    check_rows(val, 'val')
    eligible = eligible_players(train, val)
    regions = identity_regions(metadata)
    ids = [p for p in eligible if p in regions]
    report = dict(eligible_before_region=len(eligible), excluded_unknown_train_region=len(eligible)-len(ids),
                  n_gallery=len(ids), eligible_ids=ids)
    if len(ids) < 2:
        return dict(report, status='insufficient_data', reason='Need >=2 players meeting the fixed 20-game gate and known train region')
    # Scale on ALL usable training games, independent of validation eligibility.
    model = fit_gallery(train, features)
    lookup = {p: i for i, p in enumerate(model['ids'])}
    gallery = model['vectors'][[lookup[p] for p in ids]]
    query = val[val.identity_id.isin(ids)].copy()
    query[features] = (np.where(np.isfinite(query[features]), query[features], model['mean']) - model['mean'])/model['scale']
    grouped = query.groupby(['identity_id', 'series_id'], sort=True)
    q = grouped[features].mean().reset_index()
    query_rosters = grouped.roster_id.agg(lambda x: set(x)).to_list()
    # Stable and accurate squared Euclidean distances, modest Q x G x F work.
    vectors = q[features].to_numpy()
    distances = np.empty((len(q), len(ids)))
    for i, vector in enumerate(vectors):
        distances[i] = np.sum((gallery-vector)**2, axis=1)
    target = np.array([ids.index(p) for p in q.identity_id])
    rosters, teammates = context_maps(metadata)
    allowed = np.array([[not (rosters[p] & query_rosters[i]) and p not in teammates[identity]
                         for p in ids] for i, identity in enumerate(q.identity_id)])
    args = (q.series_id.to_numpy(), np.array([regions[p] for p in ids]), permutations, bootstrap, seed)
    primary = infer(distances, target, np.ones_like(allowed), *args)
    control = infer(distances, target, allowed, *args)
    report.update(status='fit', primary=primary, team_context_control=control,
                  scaling={'fit_split': 'train', 'mean': model['mean'].tolist(), 'scale': model['scale'].tolist(),
                           'all_missing_features': model['all_missing_features']})
    return report


def inventory(root):
    """Validate all metadata before array payloads; reuse existing reader."""
    pairs, audit = metadata_inventory(guard_path(root))
    rows = [row for pair in pairs for row in pair]
    check_rows(pd.DataFrame(rows))
    for path, schema in audit['schema'].items():
        guard_path(path)
        if not set(EXTRA_ARRAYS) <= schema.keys():
            raise ValueError(f'Missing player channels in {path}')
    return pairs, audit


def stage_inputs(source, destination):
    """Copy only validated allowlisted files, never recursively copy a season."""
    pairs, audit = inventory(source)
    destination = guard_path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    paths = [guard_path(Path(source)/'extraction.json')]
    for shard in audit['schema']:
        paths.extend([guard_path(shard), guard_path(Path(shard).with_suffix('.parquet'))])
    for path in paths:
        relative = path.relative_to(source)
        target = guard_path(destination/relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(guard_path(path), target)
    return {'files': len(paths), 'bytes': sum(p.stat().st_size for p in paths), 'replays': len(pairs)}


def main(argv=None):
    start = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, default=DEFAULT_COMPACT)
    parser.add_argument('--out', type=Path, default=Path('results/rq4_retrieval.json'))
    parser.add_argument('--max-replays', type=int)
    parser.add_argument('--permutations', type=int, default=2000)
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--stage-to', type=Path, help='Only stage validated compact inputs and exit')
    args = parser.parse_args(argv)
    if min(args.permutations, args.bootstrap) < 0 or (args.max_replays is not None and args.max_replays < 1):
        parser.error('Replicates must be nonnegative; replay limit must be positive')
    if args.stage_to:
        print(json.dumps(stage_inputs(args.compact, args.stage_to)))
        return
    pairs, audit = inventory(args.compact)
    metadata = [row for pair in pairs for row in pair]
    selected = pairs
    if args.max_replays is not None:
        # Earliest slices minimize repeated ZIP prefix decompression in a smoke.
        # Round robin ensures all allowed seasons are exercised; not inferential.
        buckets = {s: sorted([p for p in pairs if p[0]['season'] == s],
                             key=lambda p: (p[0]['_shard'], int(p[0]['start']))) for s in ALLOWED_SEASONS}
        selected = []
        while len(selected) < args.max_replays and any(buckets.values()):
            for season in ALLOWED_SEASONS:
                if buckets[season] and len(selected) < args.max_replays:
                    selected.append(buckets[season].pop(0))
    inventory_seconds = time.perf_counter()-start
    extraction_start = time.perf_counter()
    rows = []
    if args.max_replays is not None:
        for pair in selected:
            for meta in pair:
                rows.extend(game_features(meta, read_player_slice(meta)))
    else:
        # One shard resident at a time, reuse canonical compact reader unchanged.
        by_key = {(r['_shard'], r['replay_id'], r['focal_team']): r for r in metadata}
        for shard in sorted(audit['schema']):
            guard_path(shard)
            guard_path(Path(shard).with_suffix('.parquet'))
            for raw, arrays in iter_compact(shard, splits={'train', 'val'}):
                check_rows(pd.DataFrame([raw]))
                meta = by_key[(shard, raw['replay_id'], raw['focal_team'])]
                rows.extend(game_features(meta, arrays))
            print(f'Processed {shard}: {len(rows)} player-games', flush=True)
    feature_seconds = time.perf_counter()-extraction_start
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError('No usable player-game features')
    if frame.duplicated(['identity_id', 'season', 'replay_id']).any():
        raise ValueError('Duplicated player-game: check perspectives')
    features = sorted(c for c in frame if c.startswith('f_'))
    inference_start = time.perf_counter()
    result = evaluate_retrieval(frame[frame.split == 'train'], frame[frame.split == 'val'],
                                features, metadata, args.permutations, args.bootstrap, args.seed)
    inference_seconds = time.perf_counter()-inference_start
    selected_ids = [p[0]['replay_id'] for p in selected]
    result.update(schema_version=1, analysis='RQ4 handcrafted PLAYER identity retrieval',
                  mode='smoke' if args.max_replays is not None else 'full',
                  min_games_per_season=MIN_GAMES, train_seasons=list(TRAIN_SEASONS), val_season=VAL_SEASON,
                  test_opened=False, features=features, seed=args.seed,
                  requested_permutations=args.permutations, requested_bootstrap=args.bootstrap,
                  compact_source=str(args.compact), available_replays=len(pairs),
                  processed_replays=len(selected_ids), player_games=len(frame),
                  player_games_by_season=frame.groupby('season').size().to_dict(),
                  replay_ids=selected_ids, timings_seconds=dict(inventory=inventory_seconds, features=feature_seconds,
                      inference=inference_seconds, total=time.perf_counter()-start),
                  methods=__doc__, compact_series_completeness_certified=audit['complete_series_certified'])
    # Hash metadata, not entire multi-GB shards (record size/mtime for those).
    result['input_files'] = [{'path': p, 'bytes': Path(p).stat().st_size,
                             'mtime_ns': Path(p).stat().st_mtime_ns,
                             'metadata_sha256': hashlib.sha256(guard_path(Path(p).with_suffix('.parquet')).read_bytes()).hexdigest()}
                            for p in sorted(audit['schema'])]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'output': str(args.out), 'status': result['status'], 'mode': result['mode'],
                      'processed_replays': result['processed_replays'], 'timings_seconds': result['timings_seconds']}))


if __name__ == '__main__':
    main()
