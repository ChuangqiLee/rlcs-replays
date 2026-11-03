"""Build and load a reusable window cache for the AI experiments.

The cache is built once per compact source (a few large files on GPFS) and
loaded by every training job into node-local scratch, replacing the per-job
feature extraction. It reuses the frozen extraction helpers unchanged
(``selected_indices``, ``per_frame_tokens``, ``per_frame_features``,
``game_features``) so windows, usable games and handcrafted features are
identical to ``ai_experiments.dataset.build_dataset`` for the same config.

Additions over the original builder:
  * every window carries score/clock context and prospective goal timing
    (seconds from the window end to the next own/opponent goal, censoring),
    so the same cache serves identity and goal-risk tasks;
  * arrays are stored as float16 chunks per shard (one file per shard);
  * shards are processed in parallel worker processes.

Only explicitly allowlisted seasons are read; 2026/test is never opened.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from pilot_encoder.dataset import assert_allowed, per_frame_features, safe_inventory
from pilot_encoder.dataset_v3 import per_frame_tokens
from tactics_code.data import iter_compact, parsed_json
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, guard_path
from tactics_code.style_retrieval import game_features
from .dataset import agent_channel_summary, selected_handcrafted, selected_indices

CTX_COLUMNS = ('score_diff_start', 'remaining_start', 'overtime_start', 't_start', 't_end',
               'dt_own_goal', 'dt_opp_goal', 't_last', 'complete', 'n_valid')
INFO_COLUMNS = ('perspective', 'slot', 'start', 'length')
NO_GOAL = 1e4  # sentinel: no further goal observed for this perspective


def goal_events(arrays):
    """Goal times from focal-perspective score_diff transitions (own > 0)."""
    sd = np.asarray(arrays['score_diff'], dtype=np.float64)
    t = np.asarray(arrays['time'], dtype=np.float64)
    finite = np.isfinite(sd)
    change = finite[:-1] & finite[1:] & (sd[1:] != sd[:-1])
    idx = np.flatnonzero(change) + 1
    delta = sd[idx] - sd[idx - 1]
    return t[idx], delta


def window_context(arrays, idx, own_times, opp_times):
    """Score/clock at the window start and prospective goal timing from its end."""
    t = np.asarray(arrays['time'], dtype=np.float64)
    first, last = int(idx[0]), int(idx[-1])
    t_end = t[last]
    def next_after(times):
        later = times[times > t_end]
        return float(later.min() - t_end) if len(later) else NO_GOAL
    return [float(arrays['score_diff'][first]), float(arrays['remaining'][first]),
            float(arrays['overtime'][first]), float(t[first]), float(t_end),
            next_after(own_times), next_after(opp_times), float(np.nanmax(t)),
            float(len(idx) == int(60)), float(len(idx))]


def process_shard(args):
    shard, metas, config, out_dir, limit = args
    store_pooled = bool(config.get('store_pooled', True))
    path = guard_path(Path(shard))
    assert path.parent.name in ALLOWED_SEASONS and '2026' not in str(path)
    lookup = {(m['replay_id'], m['focal_team']): m for m in metas}
    length = int(config['window_frames'])
    agents, pooled, masks, wgame, ctx, info = [], [], [], [], [], []
    rows, done = [], 0
    started = time.perf_counter()
    for raw, arrays in iter_compact(path, splits={'train', 'val'}):
        assert_allowed(pd.DataFrame([raw]))
        meta = lookup.get((raw['replay_id'], raw['focal_team']))
        if meta is None:
            continue
        if limit and done >= limit:
            break
        done += 1
        own_t, delta = goal_events(arrays)
        own_times, opp_times = own_t[delta > 0], own_t[delta < 0]
        features = {r['identity_id']: r for r in game_features(meta, arrays)}
        ids = parsed_json(meta['player_ids'], [])
        tokens = common = None
        for slot, identity in enumerate(ids[:3]):
            if identity not in features:
                continue
            indices = selected_indices(meta, arrays, slot, config)
            if not indices:
                raise ValueError('Usable player-game has no windows')
            if tokens is None or True:  # per-slot features (query-relative); recompute
                tokens, _ = per_frame_tokens(arrays, slot)
                common, _ = per_frame_features(arrays, slot)
            selected = np.concatenate(indices)
            row = dict(features[identity])
            row['observed_seconds'] = len(selected) / float(meta['fps'])
            row['n_windows'] = len(indices)
            row['perspective'] = int(meta['_index'])
            row['slot'] = slot
            match = selected_handcrafted(meta, arrays, slot, indices)
            row['_matched'] = [float(match[c]) for c in sorted(c for c in match if c.startswith('f_'))]
            row['_summary'] = np.concatenate([common[selected].mean(0), common[selected].std(0)]).astype(np.float32).tolist()
            row['_agent_summary'] = agent_channel_summary(tokens, selected).tolist()
            row['_selection'] = [dict(start=int(i[0]), length=len(i)) for i in indices]
            game_local = len(rows)
            rows.append(row)
            for idx in indices:
                a = np.zeros((length, 7, 16), dtype=np.float16)
                a[:len(idx)] = tokens[idx]
                agents.append(a)
                if store_pooled:
                    p = np.zeros((length, 38), dtype=np.float16)
                    p[:len(idx)] = common[idx]
                    pooled.append(p)
                masks.append(np.arange(length) < len(idx))
                wgame.append(game_local)
                ctx.append(window_context(arrays, idx, own_times, opp_times))
                info.append([int(meta['_index']), slot, int(idx[0]), len(idx)])
    if not rows:
        raise ValueError(f'No usable player-games in {shard}')
    out_dir = Path(out_dir)
    name = f'chunk-{path.parent.name}-{path.stem}'
    arrays = dict(agents=np.stack(agents), masks=np.stack(masks), window_games=np.asarray(wgame, dtype=np.int32),
                  ctx=np.asarray(ctx, dtype=np.float32), info=np.asarray(info, dtype=np.int32))
    if store_pooled:
        arrays['pooled'] = np.stack(pooled)
    np.savez(out_dir / f'{name}.npz', **arrays)
    (out_dir / f'{name}.games.json').write_text(json.dumps(rows, separators=(',', ':')))
    return dict(shard=str(path), chunk=f'{name}.npz', games_file=f'{name}.games.json',
                n_games=len(rows), n_windows=len(agents), seconds=time.perf_counter() - started,
                bytes=path.stat().st_size,
                metadata_sha256=hashlib.sha256(path.with_suffix('.parquet').read_bytes()).hexdigest())


def build(compact, out_dir, config, workers=8, limit=0):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    compact = guard_path(Path(compact)).resolve()
    pairs, audit = safe_inventory(compact)
    metadata = [m for pair in pairs for m in pair]
    for i, m in enumerate(metadata):
        m['_index'] = i
    seen, series_splits = {}, {}
    for m in metadata:
        key = (m['season'], m['split'], m['series_id'])
        if m['replay_id'] in seen and seen[m['replay_id']] != key:
            raise ValueError('Replay duplicated across seasons/splits/series')
        seen[m['replay_id']] = key
        if m['series_id'] in series_splits and series_splits[m['series_id']] != key[:2]:
            raise ValueError('Observed series crosses season/split')
        series_splits[m['series_id']] = key[:2]
    shards = [s for s in sorted(audit['schema']) if Path(s).parent.name in ALLOWED_SEASONS]
    by_shard = {s: [m for m in metadata if m['_shard'] == s] for s in shards}
    tasks = [(s, by_shard[s], config, str(out_dir), limit) for s in shards]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(process_shard, tasks))
    order = {r['shard']: r for r in results}
    manifest, rows, matched, summaries, agent_summaries, selection = [], [], [], [], [], []
    game_offset = window_offset = 0
    for s in shards:
        r = order[s]
        games = json.loads((out_dir / r['games_file']).read_text())
        for g in games:
            matched.append(g.pop('_matched'))
            summaries.append(g.pop('_summary'))
            agent_summaries.append(g.pop('_agent_summary'))
            selection.append(dict(game_index=len(rows), windows=g.pop('_selection')))
            rows.append(g)
        manifest.append(dict(r, game_offset=game_offset, window_offset=window_offset))
        game_offset += r['n_games']
        window_offset += r['n_windows']
    games = pd.DataFrame(rows)
    assert_allowed(games)
    if games.duplicated(['identity_id', 'season', 'replay_id']).any():
        raise ValueError('Duplicate player-game across perspectives')
    games.to_parquet(out_dir / 'games.parquet', index=False)
    np.savez(out_dir / 'summaries.npz', matched_handcrafted=np.asarray(matched, dtype=np.float64),
             summaries=np.asarray(summaries, dtype=np.float32),
             agent_summaries=np.asarray(agent_summaries, dtype=np.float32))
    (out_dir / 'selection.json').write_text(json.dumps(selection, separators=(',', ':')))
    (out_dir / 'metadata.json').write_text(json.dumps(metadata, default=str))
    for r in results:
        (out_dir / r['games_file']).unlink()
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[2]).stdout.strip()
    report = dict(compact=str(compact), config=config, git_commit=commit, limit=limit,
                  player_games=len(games), windows=window_offset,
                  player_games_by_season=games.groupby('season').size().to_dict(),
                  windows_by_split={split: int(np.isin(np.repeat(games.split.to_numpy(),
                                                                 games.n_windows.to_numpy()), split).sum())
                                    for split in ('train', 'val')},
                  input_files=[dict(path=r['shard'], bytes=r['bytes'], metadata_sha256=r['metadata_sha256'])
                               for r in manifest],
                  chunks=manifest, ctx_columns=list(CTX_COLUMNS), info_columns=list(INFO_COLUMNS),
                  complete_series_certified=audit['complete_series_certified'],
                  seconds=time.perf_counter() - started, test_opened=False,
                  train_seasons=list(TRAIN_SEASONS), allowed_seasons=list(ALLOWED_SEASONS))
    (out_dir / 'report.json').write_text(json.dumps(report, indent=1, default=str))
    return report


def load_cache(cache_dir, scratch_dir, *, need_agents=True, need_pooled=True):
    """Materialize the cache as node-local memmaps; returns a Dataset-like object."""
    cache_dir, scratch_dir = Path(cache_dir), Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads((cache_dir / 'report.json').read_text())
    chunks = report['chunks']
    n, length = report['windows'], int(report['config']['window_frames'])
    def mm(name, dtype, shape):
        return np.lib.format.open_memmap(scratch_dir / name, mode='w+', dtype=dtype, shape=shape)
    agents = mm('agents.npy', np.float16, (n, length, 7, 16)) if need_agents else None
    if need_pooled and not report['config'].get('store_pooled', True):
        raise ValueError('This cache stores no pooled channels; load with need_pooled=False')
    pooled = mm('pooled.npy', np.float16, (n, length, 38)) if need_pooled else None
    masks = np.zeros((n, length), dtype=bool)
    window_games = np.zeros(n, dtype=np.int64)
    ctx = np.zeros((n, len(CTX_COLUMNS)), dtype=np.float32)
    info = np.zeros((n, len(INFO_COLUMNS)), dtype=np.int32)
    started = time.perf_counter()
    for c in chunks:
        with np.load(cache_dir / c['chunk'], allow_pickle=False) as z:
            o, k = c['window_offset'], c['n_windows']
            if need_agents:
                agents[o:o + k] = z['agents']
            if need_pooled:
                pooled[o:o + k] = z['pooled']
            masks[o:o + k] = z['masks']
            window_games[o:o + k] = z['window_games'].astype(np.int64) + c['game_offset']
            ctx[o:o + k] = z['ctx']
            info[o:o + k] = z['info']
    for arr in (agents, pooled):
        if arr is not None:
            arr.flush()
    games = pd.read_parquet(cache_dir / 'games.parquet')
    assert_allowed(games)
    metadata = json.loads((cache_dir / 'metadata.json').read_text())
    with np.load(cache_dir / 'summaries.npz') as z:
        matched, summaries, agent_summaries = z['matched_handcrafted'], z['summaries'], z['agent_summaries']
    report['load_seconds'] = time.perf_counter() - started
    return SimpleNamespace(x=agents, pooled_x=pooled, masks=masks, window_games=window_games,
                           games=games, metadata=metadata, audit=None, report=report,
                           matched_handcrafted=matched, summaries=summaries,
                           agent_summaries=agent_summaries, ctx=ctx, info=info,
                           ctx_columns=CTX_COLUMNS, info_columns=INFO_COLUMNS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cap', type=int, default=64, help='max windows per player-game')
    parser.add_argument('--window-frames', type=int, default=60)
    parser.add_argument('--selection-seed', type=int, default=42)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--limit', type=int, default=0, help='perspectives per shard (smoke only)')
    parser.add_argument('--no-pooled', action='store_true', help='skip the 38-channel pooled array')
    args = parser.parse_args(argv)
    if '2026' in str(args.compact) or 'test' in Path(args.compact).resolve().parts:
        parser.error('2026/test sources are forbidden')
    config = dict(window_frames=args.window_frames, max_windows_per_game=args.cap,
                  selection_seed=args.selection_seed, store_pooled=not args.no_pooled)
    report = build(args.compact, args.out, config, args.workers, args.limit)
    print(json.dumps({k: report[k] for k in ('player_games', 'windows', 'player_games_by_season',
                                               'windows_by_split', 'seconds')}), flush=True)


if __name__ == '__main__':
    main()
