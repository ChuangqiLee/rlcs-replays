"""Read-only guarded compact adapter with exact exposure-matched summaries.

Existing extraction and tactics_code remain unchanged. Only explicitly
allowlisted shards are read; arrays are cached under explicit node scratch.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from pilot_encoder.dataset import assert_allowed, per_frame_features, safe_inventory
from pilot_encoder.dataset_v3 import per_frame_tokens
from tactics_code.data import iter_compact, parsed_json
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, guard_path
from tactics_code.style_retrieval import game_features


@dataclass
class Dataset:
    x: np.ndarray
    masks: np.ndarray
    window_games: np.ndarray
    games: pd.DataFrame
    metadata: list
    audit: dict
    report: dict
    pooled_x: np.ndarray
    matched_handcrafted: np.ndarray
    summaries: np.ndarray
    agent_summaries: np.ndarray | None = None


def selected_indices(meta, arrays, slot, config):
    """Exact pilot continuity/hash-cap selection, independent of optimization seed."""
    assert_allowed(pd.DataFrame([meta]))
    _, valid = per_frame_features(arrays, slot)
    length, cap = int(config['window_frames']), int(config['max_windows_per_game'])
    if min(length, cap) < 1:
        raise ValueError('Positive window length/cap required')
    times, segment = np.asarray(arrays['time']), np.asarray(arrays['segment'])
    dt = np.diff(times, prepend=np.nan)
    connected = (valid & np.roll(valid, 1) & (segment == np.roll(segment, 1)) &
                 (dt > 0) & (dt <= 1.5 / float(meta['fps'])))
    connected[0] = False
    indices = np.flatnonzero(valid)
    if not len(indices):
        return []
    starts = np.flatnonzero(~connected[indices])
    runs = np.split(indices, starts[1:])
    candidates = [run[start:start+length] for run in runs for start in range(0, len(run), length)]
    identity = parsed_json(meta['player_ids'], [])[slot]
    seed = config.get('selection_seed', 42)
    def key(index):
        return hashlib.sha256(f'{seed}:{meta["replay_id"]}:{identity}:{index[0]}'.encode()).digest()
    return sorted(sorted(candidates, key=key)[:cap], key=lambda item: item[0])


def selected_handcrafted(meta, arrays, slot, indices):
    # Preserve the original time axis. Mask excluded frames instead of joining
    # sampled windows; onsets/differences consequently cannot bridge a gap.
    selected = np.zeros(len(arrays['time']), dtype=bool)
    selected[np.concatenate(indices)] = True
    masked = dict(arrays, live=np.asarray(arrays['live'], bool) & selected)
    identity = parsed_json(meta['player_ids'], [])[slot]
    return next(row for row in game_features(meta, masked, min_seconds=1e-8)
                if row['identity_id'] == identity)


def agent_channel_summary(values, indices):
    """Mean/SD of exact agent channels, invariant to within-role slot order.

    Aggregate over selected time and exchangeable agents within each of the
    four roles. Zero-filled unavailable agents remain included, along with
    their explicit availability/flag-known channels, exactly as in the model.
    Four roles x 16 channels x two moments = 128 features.
    """
    values = np.asarray(values)
    selected = np.asarray(indices, dtype=np.int64)
    if values.ndim != 3 or values.shape[1:] != (7, 16) or not len(selected):
        raise ValueError('Agent summary needs [T,7,16] and nonempty selected frames')
    result = []
    for slots in ((0,), (1, 2), (3, 4, 5), (6,)):
        role = values[selected][:, slots, :].reshape(-1, 16)
        result.extend((role.mean(axis=0), role.std(axis=0)))
    return np.concatenate(result).astype(np.float32)


def build_dataset(compact, cache_dir, config, *, train_only=False):
    cache_dir = Path(cache_dir).resolve()
    scratch = Path(os.environ.get('TMPDIR', '/tmp')).resolve()
    if scratch == Path('/') or scratch not in cache_dir.parents:
        raise ValueError('AI cache must be below explicit TMPDIR (or /tmp locally)')
    cache_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    compact = guard_path(compact).resolve()
    pairs, audit = safe_inventory(compact)
    # Inventory validates allowed metadata/headers, but training-only diagnostics
    # never materialize 2025 trajectory payloads or use 2025 eligibility.
    metadata = [m for pair in pairs for m in pair
                if not train_only or m['season'] in TRAIN_SEASONS]
    seen = {}
    for m in metadata:
        key = m['replay_id']
        split_key = (m['season'], m['split'], m['series_id'])
        if key in seen and seen[key] != split_key:
            raise ValueError('Replay duplicated across seasons/splits/series')
        seen[key] = split_key
    series_splits = {}
    for m in metadata:
        key = m['series_id']
        value = (m['season'], m['split'])
        if key in series_splits and series_splits[key] != value:
            raise ValueError('Observed series crosses season/split')
        series_splits[key] = value
    lookup = {(m['_shard'], m['replay_id'], m['focal_team']): m for m in metadata}
    max_windows = len(metadata) * 3 * int(config['max_windows_per_game'])
    length = int(config['window_frames'])
    def allocate(name, dtype, shape):
        return np.lib.format.open_memmap(cache_dir / name, mode='w+', dtype=dtype, shape=shape)
    x = allocate('agents.npy', np.float32, (max_windows, length, 7, 16))
    pooled = allocate('pooled.npy', np.float32, (max_windows, length, 38))
    masks = allocate('masks.npy', np.bool_, (max_windows, length))
    window_games = allocate('window_games.npy', np.int64, (max_windows,))
    rows, matched, summaries, agent_summaries, selections, inputs = [], [], [], [], [], []
    n = 0
    for shard in sorted(audit['schema']):
        path = guard_path(shard)
        if path.parent.name not in (TRAIN_SEASONS if train_only else ALLOWED_SEASONS):
            continue
        inputs.append(dict(path=str(path), bytes=path.stat().st_size,
                           metadata_sha256=hashlib.sha256(path.with_suffix('.parquet').read_bytes()).hexdigest()))
        for raw, arrays in iter_compact(path, splits={'train'} if train_only else {'train', 'val'}):
            assert_allowed(pd.DataFrame([raw]))
            meta = lookup.get((shard, raw['replay_id'], raw['focal_team']))
            if meta is None:
                continue
            features = {r['identity_id']: r for r in game_features(meta, arrays)}
            for slot, identity in enumerate(parsed_json(meta['player_ids'], [])[:3]):
                if identity not in features:
                    continue
                indices = selected_indices(meta, arrays, slot, config)
                if not indices:
                    raise ValueError('Usable player-game has no windows')
                values, _ = per_frame_tokens(arrays, slot)
                common, _ = per_frame_features(arrays, slot)
                selected = np.concatenate(indices)
                row = features[identity]
                row['observed_seconds'] = len(selected)/float(meta['fps'])
                game_index = len(rows)
                rows.append(row)
                match = selected_handcrafted(meta, arrays, slot, indices)
                cols = sorted(c for c in match if c.startswith('f_'))
                matched.append([match[c] for c in cols])
                summaries.append(np.concatenate([common[selected].mean(0), common[selected].std(0)]))
                agent_summaries.append(agent_channel_summary(values, selected))
                selections.append(dict(game_index=game_index,
                                       windows=[dict(start=int(idx[0]), length=len(idx)) for idx in indices]))
                for idx in indices:
                    masks[n] = np.arange(length) < len(idx)
                    x[n] = 0
                    pooled[n] = 0
                    x[n, :len(idx)] = values[idx]
                    pooled[n, :len(idx)] = common[idx]
                    window_games[n] = game_index
                    n += 1
        print(json.dumps(dict(shard=str(path), player_games=len(rows), windows=n)), flush=True)
    if not rows:
        raise ValueError('No usable allowed player-games')
    games = pd.DataFrame(rows)
    assert_allowed(games)
    if games.duplicated(['identity_id', 'season', 'replay_id']).any():
        raise ValueError('Duplicate player-game across perspectives')
    for array in (x, pooled, masks, window_games):
        array.flush()
    # Retain compact selection provenance, never raw replay payloads in results.
    selection_path = cache_dir / 'selection.json'
    selection_path.write_text(json.dumps(selections, separators=(',', ':')))
    report = dict(player_games=len(games), player_games_by_season=games.groupby('season').size().to_dict(),
                  windows=n, input_files=inputs, replay_ids=sorted(seen),
                  selection_sha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
                  selection_file=str(selection_path), selection_seed=config.get('selection_seed', 42),
                  seconds=float(games.observed_seconds.sum()),
                  feature_seconds=time.perf_counter()-started, train_only=train_only, test_opened=False,
                  complete_series_certified=audit['complete_series_certified'])
    return Dataset(x[:n], masks[:n], window_games[:n], games, metadata, audit, report,
                   pooled[:n], np.asarray(matched), np.asarray(summaries, dtype=np.float32),
                   np.asarray(agent_summaries, dtype=np.float32))
