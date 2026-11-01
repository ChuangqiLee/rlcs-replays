"""Guarded compact reader and bounded, player-conditioned trajectory windows."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from tactics_code.data import iter_compact, parsed_json
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, guard_path
from tactics_code.style_retrieval import check_rows, game_features, inventory, stage_inputs

SCALE = np.array([4096, 5120, 2044, 2300, 2300, 2300], dtype=np.float32)
AXES = ('x', 'y', 'z', 'vx', 'vy', 'vz')
FLAG_NAMES = ('dodge', 'jump', 'double_jump', 'any_jump')
CHANNELS = ([f'own_{a}' for a in AXES] + ['own_boost'] +
            [f'flag_{a}' for a in FLAG_NAMES] + [f'flag_known_{a}' for a in FLAG_NAMES] +
            [f'ball_relative_{a}' for a in AXES] + ['ball_known'] +
            [f'{group}_{a}' for group in ('teammate', 'opponent')
             for a in (*[f'relative_mean_{a}' for a in AXES], 'boost_mean', 'available_fraction')])
assert len(CHANNELS) == 38
assert ALLOWED_SEASONS == ('rlcs-21-22', 'rlcs-22-23', 'rlcs-2024', 'rlcs-2025')
assert 'rlcs-2026' not in ALLOWED_SEASONS


@dataclass
class Dataset:
    x: np.ndarray
    masks: np.ndarray
    window_games: np.ndarray
    games: pd.DataFrame
    metadata: list
    audit: dict
    report: dict


def assert_allowed(frame):
    check_rows(frame)
    assert set(frame.season) <= set(ALLOWED_SEASONS), '2026/test is forbidden'
    assert not frame.season.astype(str).str.contains('2026').any(), '2026 must never be opened'


def safe_inventory(compact):
    """Allowlist metadata before any payload; no recursive discovery."""
    compact = guard_path(compact)
    # The frozen inventory checks NPZ headers before its row loop. Preflight
    # metadata here so even headers of a mislabeled shard remain unopened.
    for season in ALLOWED_SEASONS:
        assert '2026' not in season
        for path in sorted(guard_path(compact/season).glob('compact-*.parquet')):
            table = pd.read_parquet(guard_path(path))
            assert_allowed(table)
            if not table.season.eq(season).all():
                raise ValueError('Metadata season must match its allowlisted directory')
    pairs, audit = inventory(compact)
    assert_allowed(pd.DataFrame([m for pair in pairs for m in pair]))
    for shard, schema in audit['schema'].items():
        path = guard_path(shard)
        assert path.parent.name in ALLOWED_SEASONS, 'Never open 2026'
        for name, tail in [('players', [6, 8]), ('ball', [6]), ('flags', [6, 4])]:
            if schema[name]['shape'][1:] != tail:
                raise ValueError(f'{name}: expected compact trailing shape {tail}')
    return pairs, audit


def stage_compact(source, destination):
    """Reuse RQ4 staging after an additional explicit season assertion."""
    source = guard_path(source).resolve()
    safe_inventory(source)
    destination = guard_path(destination)
    report = stage_inputs(source, destination)
    # RQ4's optional decode-exclusion list is metadata, not a season discovery.
    # Preserve it if present so staging retains the original usable population.
    exclusions = guard_path(source/'decode_exclusions.json')
    if exclusions.exists():
        import shutil
        shutil.copyfile(exclusions, guard_path(destination/'decode_exclusions.json'))
        report['files'] += 1
        report['bytes'] += exclusions.stat().st_size
    safe_inventory(destination)
    return report


def per_frame_features(arrays, slot):
    """Return physically scaled X[L,38], focal valid[L]; no learned statistics."""
    if slot not in (0, 1, 2):
        raise ValueError('Only own-team slots 0,1,2 define player-games')
    p = np.asarray(arrays['players'], dtype=np.float32)
    own = p[:, slot]
    t = np.asarray(arrays['time'])
    valid = (arrays['live'].astype(bool) & (arrays['segment'] >= 0) & np.isfinite(t) &
             np.isfinite(own[:, :7]).all(axis=1) & (own[:, 7] != 1))
    flags = np.asarray(arrays['flags'][:, slot, :4])
    flag_known = np.isfinite(flags)
    ball = np.asarray(arrays['ball'][:, :6], dtype=np.float32)
    ball_known = np.isfinite(ball).all(axis=1)
    output = [own[:, :6] / SCALE, own[:, 6:7] / 255.,
              (flag_known & (flags > 0)).astype(np.float32), flag_known.astype(np.float32),
              np.where(ball_known[:, None], (ball-own[:, :6])/SCALE, 0),
              ball_known[:, None].astype(np.float32)]
    for slots in ([j for j in range(3) if j != slot], [3, 4, 5]):
        neighbors = p[:, slots]
        known = np.isfinite(neighbors[:, :, :7]).all(axis=2) & (neighbors[:, :, 7] != 1)
        count = known.sum(axis=1)[:, None]
        # Mask before summation; no NaN*0 propagation for absent neighbors.
        relative = (neighbors[:, :, :6]-own[:, None, :6]) / SCALE
        mean = np.where(known[:, :, None], relative, 0).sum(axis=1) / np.maximum(count, 1)
        boost = np.where(known, neighbors[:, :, 6]/255., 0).sum(axis=1)[:, None] / np.maximum(count, 1)
        output.extend([mean, boost, count / len(slots)])
    x = np.concatenate(output, axis=1).astype(np.float32)
    x[~valid] = 0
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite scaled focal features')
    return x, valid


def player_windows(meta, arrays, slot, config):
    """Non-overlapping contiguous valid runs; hash-capped, tails right-padded."""
    assert_allowed(pd.DataFrame([meta]))
    length, cap = int(config.get('window_frames', 60)), int(config.get('max_windows_per_game', 8))
    if length < 1 or cap < 1:
        raise ValueError('Window length and cap must be positive')
    x, valid = per_frame_features(arrays, slot)
    if valid.sum()/float(meta['fps']) < 10.:
        return []
    times, segment = np.asarray(arrays['time']), np.asarray(arrays['segment'])
    dt = np.diff(times, prepend=np.nan)
    connected = (valid & np.roll(valid, 1) & (segment == np.roll(segment, 1)) &
                 (dt > 0) & (dt <= 1.5/float(meta['fps'])))
    connected[0] = False
    indices = np.flatnonzero(valid)
    run_starts = np.flatnonzero(~connected[indices])
    runs = np.split(indices, run_starts[1:])
    candidates = [(int(run[start]), run[start:start+length]) for run in runs
                  for start in range(0, len(run), length)]
    identity = parsed_json(meta['player_ids'], [])[slot]
    seed = int(config.get('seed', 42))
    def priority(item):
        return hashlib.sha256(f'{seed}:{meta["replay_id"]}:{identity}:{item[0]}'.encode()).digest()
    selected = sorted(sorted(candidates, key=priority)[:cap], key=lambda item: item[0])
    windows = []
    for _, indices in selected:
        frame = np.zeros((length, len(CHANNELS)), dtype=np.float32)
        mask = np.arange(length) < len(indices)
        frame[mask] = x[indices]
        windows.append((frame, mask))
    return windows


def build_dataset(compact, cache_dir, config):
    """One shard resident at a time, bounded windows written to disk-backed arrays."""
    # Reuse the same checkpoint/cache destination policy without importing torch.
    import os
    cache_dir = Path(cache_dir).resolve()
    roots = [(Path(__file__).resolve().parents[2]/'artifacts'/'pilot_encoder').resolve()]
    if os.environ.get('TMPDIR'):
        scratch = Path(os.environ['TMPDIR']).resolve()
        if scratch == Path('/'):
            raise ValueError('TMPDIR must not be root')
        roots.append(scratch)
    if not any(cache_dir == root or root in cache_dir.parents for root in roots):
        raise ValueError('Cache must be under $TMPDIR or artifacts/pilot_encoder/')
    cache_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    pairs, audit = safe_inventory(compact)
    metadata = [m for pair in pairs for m in pair]
    lookup = {(m['_shard'], m['replay_id'], m['focal_team']): m for m in metadata}
    inventory_seconds = time.perf_counter()-started
    max_windows = len(pairs)*6*int(config['max_windows_per_game'])
    shape = (max_windows, int(config['window_frames']), len(CHANNELS))
    x = np.lib.format.open_memmap(cache_dir/'windows.npy', mode='w+', dtype=np.float32, shape=shape)
    masks = np.lib.format.open_memmap(cache_dir/'masks.npy', mode='w+', dtype=np.bool_, shape=shape[:2])
    window_games = np.lib.format.open_memmap(cache_dir/'window_games.npy', mode='w+', dtype=np.int64, shape=(max_windows,))
    rows, n, inputs = [], 0, []
    extraction_start = time.perf_counter()
    for shard in sorted(audit['schema']):
        path = guard_path(shard)
        assert path.parent.name in ALLOWED_SEASONS and '2026' not in str(path)
        meta_path = guard_path(path.with_suffix('.parquet'))
        inputs.append({'path': str(path), 'bytes': path.stat().st_size,
                       'mtime_ns': path.stat().st_mtime_ns,
                       'metadata_sha256': hashlib.sha256(meta_path.read_bytes()).hexdigest()})
        # IMPORTANT: passing this explicit file never invokes iter_compact rglob.
        for raw, arrays in iter_compact(path, splits={'train', 'val'}):
            assert_allowed(pd.DataFrame([raw]))
            key = (shard, raw['replay_id'], raw['focal_team'])
            if key not in lookup:  # metadata inventory's decode exclusions, if any
                continue
            meta = lookup[key]
            features = {r['identity_id']: r for r in game_features(meta, arrays)}
            ids = parsed_json(meta['player_ids'], [])
            for slot, identity in enumerate(ids[:3]):
                if identity not in features:
                    continue
                windows = player_windows(meta, arrays, slot, config)
                if not windows:
                    raise AssertionError('RQ4-usable game must have a window')
                game_index = len(rows)
                rows.append(features[identity])
                for frame, mask in windows:
                    x[n], masks[n], window_games[n] = frame, mask, game_index
                    n += 1
        print(json.dumps({'shard': str(path), 'player_games': len(rows), 'windows': n}), flush=True)
    if not rows:
        raise ValueError('No RQ4-usable player-games')
    games = pd.DataFrame(rows)
    assert_allowed(games)
    if games.duplicated(['identity_id', 'season', 'replay_id']).any():
        raise ValueError('Duplicate player-game from perspectives')
    for array in (x, masks, window_games):
        array.flush()
    report = {'available_replays': len(pairs), 'processed_replays': len(pairs),
              'player_games': len(games), 'player_games_by_season': games.groupby('season').size().to_dict(),
              'windows': n, 'windows_by_split': {split: int(np.isin(window_games[:n], np.flatnonzero(games.split == split)).sum())
                                               for split in ('train', 'val')},
              'input_shape': [n, shape[1], shape[2]], 'input_channels': CHANNELS,
              'input_files': inputs, 'replay_ids': [pair[0]['replay_id'] for pair in pairs],
              'compact_series_completeness_certified': audit['complete_series_certified'],
              'timings_seconds': {'inventory': inventory_seconds, 'features': time.perf_counter()-extraction_start},
              'test_opened': False}
    return Dataset(x[:n], masks[:n], window_games[:n], games, metadata, audit, report)
