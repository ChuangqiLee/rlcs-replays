"""V3-only seven-agent windows; the V1/V2 dataset path remains unchanged.

The frozen builder supplies inventory guards, focal validity and handcrafted
usable-game rows. Window selection is deliberately identical to its fixed
algorithm; tests compare every synthetic window and game against that builder.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from tactics_code.data import iter_compact, parsed_json
from tactics_code.screen import ALLOWED_SEASONS, guard_path
from tactics_code.style_retrieval import game_features

from .dataset import (AXES, FLAG_NAMES, SCALE, Dataset, assert_allowed,
                      per_frame_features, safe_inventory)

CHANNELS = ([f'trajectory_{axis}' for axis in AXES] + ['boost'] +
            [f'flag_{name}' for name in FLAG_NAMES] +
            [f'flag_known_{name}' for name in FLAG_NAMES] + ['available'])
AGENT_ROLES = ['query', 'teammate', 'teammate', 'opponent', 'opponent', 'opponent', 'ball']
assert len(CHANNELS) == 16


def per_frame_tokens(arrays, slot):
    """Return X[L,7,16] and unchanged focal validity, without identity channels."""
    # Reusing this function also preserves the exact V1/V2 focal-valid predicate.
    _, valid = per_frame_features(arrays, slot)
    players = np.asarray(arrays['players'], dtype=np.float32)
    flags = np.asarray(arrays['flags'], dtype=np.float32)
    own = players[:, slot]
    order = [slot] + [other for other in range(3) if other != slot] + [3, 4, 5]
    cars = players[:, order]
    available = np.isfinite(cars[:, :, :7]).all(axis=2) & (cars[:, :, 7] != 1)
    output = np.zeros((len(players), 7, len(CHANNELS)), dtype=np.float32)
    # np.where removes nonfinite missing-track values before they enter model
    # inputs. Invalid focal frames are entirely discarded below.
    relative = (cars[:, :, :6] - own[:, None, :6]) / SCALE
    relative[:, 0] = own[:, :6] / SCALE
    output[:, :6, :6] = np.where(available[:, :, None], relative, 0)
    output[:, :6, 6] = np.where(available, cars[:, :, 6] / 255., 0)
    car_flags = flags[:, order, :4]
    known_flags = np.isfinite(car_flags) & available[:, :, None]
    output[:, :6, 7:11] = known_flags & (car_flags > 0)
    output[:, :6, 11:15] = known_flags
    output[:, :6, 15] = available
    ball = np.asarray(arrays['ball'], dtype=np.float32)[:, :6]
    ball_known = np.isfinite(ball).all(axis=1)
    output[:, 6, :6] = np.where(ball_known[:, None], (ball - own[:, :6]) / SCALE, 0)
    output[:, 6, 15] = ball_known
    output[~valid] = 0
    if not np.isfinite(output).all():
        raise ValueError('Nonfinite scaled multi-agent features')
    return output, valid


def player_windows(meta, arrays, slot, config):
    """The frozen discontinuity, tail-padding and SHA256 capping rules, for V3."""
    assert_allowed(pd.DataFrame([meta]))
    length = int(config.get('window_frames', 60))
    cap = int(config.get('max_windows_per_game', 8))
    if length < 1 or cap < 1:
        raise ValueError('Window length and cap must be positive')
    values, valid = per_frame_tokens(arrays, slot)
    if valid.sum() / float(meta['fps']) < 10.:
        return []
    times, segment = np.asarray(arrays['time']), np.asarray(arrays['segment'])
    dt = np.diff(times, prepend=np.nan)
    connected = (valid & np.roll(valid, 1) & (segment == np.roll(segment, 1)) &
                 (dt > 0) & (dt <= 1.5 / float(meta['fps'])))
    connected[0] = False
    indices = np.flatnonzero(valid)
    run_starts = np.flatnonzero(~connected[indices])
    runs = np.split(indices, run_starts[1:])
    candidates = [(int(run[start]), run[start:start + length]) for run in runs
                  for start in range(0, len(run), length)]
    identity = parsed_json(meta['player_ids'], [])[slot]
    seed = int(config.get('seed', 42))

    def priority(item):
        return hashlib.sha256(f'{seed}:{meta["replay_id"]}:{identity}:{item[0]}'.encode()).digest()

    selected = sorted(sorted(candidates, key=priority)[:cap], key=lambda item: item[0])
    windows = []
    for _, indices in selected:
        frame = np.zeros((length, 7, len(CHANNELS)), dtype=np.float32)
        mask = np.arange(length) < len(indices)
        frame[mask] = values[indices]
        windows.append((frame, mask))
    return windows


def build_dataset(compact, cache_dir, config):
    """Guarded single-shard extraction into a V3-only disk-backed agent cache."""
    cache_dir = Path(cache_dir).resolve()
    roots = [(Path(__file__).resolve().parents[2] / 'artifacts' / 'pilot_encoder').resolve()]
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
    metadata = [meta for pair in pairs for meta in pair]
    lookup = {(meta['_shard'], meta['replay_id'], meta['focal_team']): meta for meta in metadata}
    inventory_seconds = time.perf_counter() - started
    max_windows = len(pairs) * 6 * int(config['max_windows_per_game'])
    shape = (max_windows, int(config['window_frames']), 7, len(CHANNELS))
    x = np.lib.format.open_memmap(cache_dir / 'windows.npy', mode='w+', dtype=np.float32, shape=shape)
    masks = np.lib.format.open_memmap(cache_dir / 'masks.npy', mode='w+', dtype=np.bool_, shape=shape[:2])
    window_games = np.lib.format.open_memmap(cache_dir / 'window_games.npy', mode='w+',
                                           dtype=np.int64, shape=(max_windows,))
    rows, n, inputs = [], 0, []
    extraction_start = time.perf_counter()
    for shard in sorted(audit['schema']):
        path = guard_path(shard)
        assert path.parent.name in ALLOWED_SEASONS and '2026' not in str(path)
        meta_path = guard_path(path.with_suffix('.parquet'))
        inputs.append({'path': str(path), 'bytes': path.stat().st_size,
                       'mtime_ns': path.stat().st_mtime_ns,
                       'metadata_sha256': hashlib.sha256(meta_path.read_bytes()).hexdigest()})
        # Explicit validated shard path: no recursive compact-root reader.
        for raw, arrays in iter_compact(path, splits={'train', 'val'}):
            assert_allowed(pd.DataFrame([raw]))
            key = (shard, raw['replay_id'], raw['focal_team'])
            if key not in lookup:
                continue
            meta = lookup[key]
            features = {row['identity_id']: row for row in game_features(meta, arrays)}
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
    report = {
        'available_replays': len(pairs), 'processed_replays': len(pairs),
        'player_games': len(games), 'player_games_by_season': games.groupby('season').size().to_dict(),
        'windows': n,
        'windows_by_split': {split: int(np.isin(window_games[:n], np.flatnonzero(games.split == split)).sum())
                             for split in ('train', 'val')},
        'input_shape': [n, *shape[1:]], 'input_channels': CHANNELS, 'agent_roles': AGENT_ROLES,
        'input_files': inputs, 'replay_ids': [pair[0]['replay_id'] for pair in pairs],
        'compact_series_completeness_certified': audit['complete_series_certified'],
        'timings_seconds': {'inventory': inventory_seconds,
                           'features': time.perf_counter() - extraction_start},
        'test_opened': False,
    }
    return Dataset(x[:n], masks[:n], window_games[:n], games, metadata, audit, report)
