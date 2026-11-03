"""Prospective goal-risk dataset: frames, fixed anchor grid, competing first-goal labels.

For every allowlisted perspective the builder stores a team-canonical absolute
frame tensor ``[L,7,16]`` (own three cars, opposing three cars, ball), per-frame
scalars, decoded goal events, a past-only anchor eligibility flag, anchors on a
0.5 s grid with a series-hashed phase (1 s sub-grid flagged for evaluation),
competing first-goal labels at 10 s and 20 s horizons with explicit censoring,
and snapshot handcrafted features for the tabular comparators. Nothing uses
information after the anchor time except the labels themselves. 2026/test is
never opened.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from pilot_encoder.dataset import assert_allowed, safe_inventory
from tactics_code.data import iter_compact, parsed_json
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, guard_path
from .cache import goal_events

SCALE = np.array([4096, 5120, 2044, 2300, 2300, 2300], dtype=np.float32)
HORIZONS = (10., 20.)
HISTORY = 60
ANCHOR_COLUMNS = ('perspective', 'frame', 'time', 'score_diff', 'remaining', 'overtime', 'on_1s_grid',
                  'y10', 'y20', 'dt_own', 'dt_opp', 'terminal', 'L', 'D', 'ball_y', 'segment_age')
FEATURE_NAMES = None  # filled by snapshot_features


def frame_tokens(arrays):
    """Absolute team-canonical tokens [L,7,16]; unavailable agents are zero with available=0."""
    players = np.asarray(arrays['players'], dtype=np.float32)
    flags = np.asarray(arrays['flags'], dtype=np.float32)
    ball = np.asarray(arrays['ball'], dtype=np.float32)[:, :6]
    L = len(players)
    out = np.zeros((L, 7, 16), dtype=np.float32)
    available = np.isfinite(players[:, :, :7]).all(axis=2) & (players[:, :, 7] != 1)
    kin = np.where(available[:, :, None], players[:, :, :6] / SCALE, 0.)
    out[:, :6, :6] = kin
    out[:, :6, 6] = np.where(available, players[:, :, 6] / 255., 0.)
    known = np.isfinite(flags[:, :, :4]) & available[:, :, None]
    out[:, :6, 7:11] = known & (flags[:, :, :4] > 0)
    out[:, :6, 11:15] = known
    out[:, :6, 15] = available
    ball_known = np.isfinite(ball).all(axis=1)
    out[:, 6, :6] = np.where(ball_known[:, None], ball / SCALE, 0.)
    out[:, 6, 15] = ball_known
    if not np.isfinite(out).all():
        raise ValueError('Nonfinite frame tokens')
    return out, available, ball_known


def eligibility(arrays, available, ball_known, fps):
    """Past-only anchor eligibility: a clean 60-frame live history ending at the frame."""
    t = np.asarray(arrays['time'], dtype=np.float64)
    live = np.asarray(arrays['live'], dtype=bool)
    seg = np.asarray(arrays['segment'])
    sd = np.asarray(arrays['score_diff'], dtype=np.float32)
    players = np.asarray(arrays['players'], dtype=np.float32)
    dt = np.diff(t, prepend=np.nan)
    same = np.r_[False, seg[1:] == seg[:-1]]
    dt_ok = (dt > 0) & (dt <= 1.6 / fps)
    frame_ok = live & (seg >= 0) & available.all(axis=1) & ball_known & np.isfinite(sd)
    # Frozen coordinates (stale tracks / demolitions) for >= 1 s invalidate the frame.
    pos = players[:, :, :3]
    moved = np.r_[np.ones((1, 6), dtype=bool), np.any(pos[1:] != pos[:-1], axis=2)]
    frozen = np.zeros(len(pos), dtype=np.int32)
    run = np.zeros(6, dtype=np.int32)
    for i in range(len(pos)):
        run = np.where(moved[i], 0, run + 1)
        frozen[i] = run.max()
    frame_ok &= frozen < int(fps)
    # Within-window continuity: every frame after the first must connect to its predecessor.
    connect = same & dt_ok
    ok = frame_ok.astype(np.int32)
    con = connect.astype(np.int32)
    cs_ok = np.cumsum(ok)
    cs_con = np.cumsum(con)
    idx = np.arange(len(ok))
    start = idx - HISTORY + 1
    valid = start >= 0
    window_ok = np.zeros(len(ok), dtype=bool)
    s = start[valid]
    e = idx[valid]
    all_ok = (cs_ok[e] - np.where(s > 0, cs_ok[s - 1], 0)) == HISTORY
    all_con = (cs_con[e] - cs_con[s]) == HISTORY - 1
    window_ok[valid] = all_ok & all_con
    return window_ok, frozen


def snapshot_features(arrays, idx):
    """Handcrafted current-state features for the tabular comparators (frame idx only)."""
    p = np.asarray(arrays['players'], dtype=np.float32)[idx]  # [A,6,8]
    b = np.asarray(arrays['ball'], dtype=np.float32)[idx, :6]
    sd = np.asarray(arrays['score_diff'], dtype=np.float32)[idx]
    rem = np.asarray(arrays['remaining'], dtype=np.float32)[idx]
    ot = np.asarray(arrays['overtime'], dtype=np.float32)[idx]
    names, cols = [], []
    for team, slots in (('own', slice(0, 3)), ('opp', slice(3, 6))):
        cars = p[:, slots, :7]
        order = np.argsort(cars[:, :, 1], axis=1)
        sorted_cars = np.take_along_axis(cars, order[:, :, None], axis=1)
        for k in range(3):
            for j, ch in enumerate(('x', 'y', 'z', 'vx', 'vy', 'vz', 'boost')):
                names.append(f'{team}{k}_{ch}')
                cols.append(sorted_cars[:, k, j])
        xy = cars[:, :, :2]
        cen = xy.mean(1)
        names += [f'{team}_cx', f'{team}_cy', f'{team}_spread', f'{team}_boost_sum', f'{team}_boost_min',
                  f'{team}_boost_max', f'{team}_airborne', f'{team}_supersonic', f'{team}_goalside',
                  f'{team}_near_ball', f'{team}_closing']
        spread = np.sqrt(((xy - cen[:, None]) ** 2).sum(2)).mean(1)
        speed = np.linalg.norm(cars[:, :, 3:6], axis=2)
        d_ball = np.linalg.norm(cars[:, :, :3] - b[:, None, :3], axis=2)
        rel_v = ((cars[:, :, :3] - b[:, None, :3]) * (cars[:, :, 3:6] - b[:, None, 3:6])).sum(2) / np.maximum(d_ball, 1.)
        goalside = (cars[:, :, 1] < b[:, None, 1]) if team == 'own' else (cars[:, :, 1] > b[:, None, 1])
        cols += [cen[:, 0], cen[:, 1], spread, cars[:, :, 6].sum(1), cars[:, :, 6].min(1), cars[:, :, 6].max(1),
                 (cars[:, :, 2] > 300).sum(1), (speed >= 2200).sum(1), goalside.sum(1), d_ball.min(1), rel_v.min(1)]
    own_y = p[:, :3, 1]
    opp_y = p[:, 3:, 1]
    L = own_y.min(1) + 5120.
    D = b[:, 1] - own_y.min(1)
    names += ['ball_x', 'ball_y', 'ball_z', 'ball_vx', 'ball_vy', 'ball_vz', 'ball_speed',
              'ball_dist_own_goal', 'ball_dist_opp_goal', 'ball_tt_own_goal', 'ball_tt_opp_goal',
              'L', 'D', 'opp_last_depth', 'remaining', 'remaining_sq', 'score_diff', 'overtime', 'zero_clock']
    speed_b = np.linalg.norm(b[:, 3:6], axis=1)
    d_own = np.linalg.norm(b[:, :3] - np.array([0, -5120, 0], dtype=np.float32), axis=1)
    d_opp = np.linalg.norm(b[:, :3] - np.array([0, 5120, 0], dtype=np.float32), axis=1)
    tt_own = np.clip(np.where(b[:, 4] < -1, (b[:, 1] + 5120) / np.maximum(-b[:, 4], 1), 30.), 0, 30)
    tt_opp = np.clip(np.where(b[:, 4] > 1, (5120 - b[:, 1]) / np.maximum(b[:, 4], 1), 30.), 0, 30)
    cols += [b[:, 0], b[:, 1], b[:, 2], b[:, 3], b[:, 4], b[:, 5], speed_b, d_own, d_opp, tt_own, tt_opp,
             L, D, 5120. - opp_y.max(1), rem, rem ** 2, sd, ot, (rem <= 0).astype(np.float32)]
    out = np.stack(cols, axis=1).astype(np.float32)
    return out, names, L, D


def terminal_certified(arrays, own_t, opp_t):
    """True when the recorded perspective ends with the game decided."""
    live = np.asarray(arrays['live'], dtype=bool)
    if not live.any():
        return False
    last = int(np.flatnonzero(live)[-1])
    rem = float(arrays['remaining'][last])
    ot = float(arrays['overtime'][last])
    sd = float(arrays['score_diff'][last])
    t = np.asarray(arrays['time'], dtype=np.float64)
    goals = np.sort(np.r_[own_t, opp_t])
    ot_frames = np.flatnonzero(np.asarray(arrays['overtime'], dtype=np.float32) > 0)
    if len(ot_frames) and len(goals) and goals[-1] >= t[ot_frames[0]]:
        return True  # golden goal in overtime
    return bool(rem <= 0 and ot == 0 and sd != 0)


def labels_for(t, own_t, opp_t, t_end, certified):
    """Competing first goal within each horizon; -1 marks censored anchors."""
    goals = np.r_[own_t, opp_t]
    kinds = np.r_[np.ones(len(own_t), dtype=np.int8), np.full(len(opp_t), 2, dtype=np.int8)]
    order = np.argsort(goals)
    goals, kinds = goals[order], kinds[order]
    def next_after(times, values=None):
        if not len(times):
            return np.full(len(t), np.inf), np.zeros(len(t), dtype=np.int8)
        pos = np.searchsorted(times, t, side='right')
        has = pos < len(times)
        safe = np.minimum(pos, len(times) - 1)
        nxt = np.where(has, times[safe], np.inf)
        kind = np.where(has, values[safe], 0).astype(np.int8) if values is not None else None
        return nxt, kind
    next_t, next_kind = next_after(goals, kinds)
    dt_next = next_t - t
    dt_own = next_after(own_t)[0] - t
    dt_opp = next_after(opp_t)[0] - t
    out = {}
    for h in HORIZONS:
        y = np.where(dt_next <= h, next_kind, 0).astype(np.int8)
        observed = (dt_next <= h) | (t + h <= t_end) | certified
        y[~observed] = -1
        out[f'y{int(h)}'] = y
    return out, dt_own, dt_opp


def process_shard(args):
    shard, metas, out_dir, stride = args
    path = guard_path(Path(shard))
    assert path.parent.name in ALLOWED_SEASONS and '2026' not in str(path)
    lookup = {(m['replay_id'], m['focal_team']): m for m in metas}
    frames, persp_rows, anchor_rows, feats, elig_all = [], [], [], [], []
    offset = 0
    started = time.perf_counter()
    feature_names = None
    for raw, arrays in iter_compact(path, splits={'train', 'val'}):
        assert_allowed(pd.DataFrame([raw]))
        meta = lookup.get((raw['replay_id'], raw['focal_team']))
        if meta is None:
            continue
        fps = float(meta['fps'])
        tokens, available, ball_known = frame_tokens(arrays)
        window_ok, frozen = eligibility(arrays, available, ball_known, fps)
        t = np.asarray(arrays['time'], dtype=np.float64)
        goal_t, delta = goal_events(arrays)
        own_t, opp_t = np.sort(goal_t[delta > 0]), np.sort(goal_t[delta < 0])
        certified = terminal_certified(arrays, own_t, opp_t)
        # Anchor grid: 0.5 s spacing with a series-hashed phase, snapped to recorded frames.
        phase = int(hashlib.sha256(f'42:{meta["series_id"]}'.encode()).hexdigest()[:8], 16) % 5 / 10.
        t0 = np.nanmin(t)
        grid = np.arange(t0 + phase, np.nanmax(t) + 1e-9, stride)
        idx = np.searchsorted(t, grid, side='right') - 1
        idx = idx[(idx >= 0) & (idx < len(t))]
        idx = np.unique(idx[np.abs(t[idx] - grid[:len(idx)]) <= 0.15]) if len(idx) else idx
        idx = idx[window_ok[idx]]
        if len(idx):
            on_1s = (np.round((t[idx] - t0 - phase) / stride).astype(np.int64) % int(round(1. / stride))) == 0
            lab, dt_own, dt_opp = labels_for(t[idx], own_t, opp_t, float(np.nanmax(t)), certified)
            f, feature_names, L, D = snapshot_features(arrays, idx)
            seg = np.asarray(arrays['segment'])
            seg_start = np.zeros(len(t))
            # time since the start of the current live segment (history summary, excluded from primary inputs)
            starts = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
            seg_start_time = np.repeat(t[starts], np.diff(np.r_[starts, len(t)]))
            age = t[idx] - seg_start_time[idx]
            rows = np.column_stack([np.full(len(idx), len(persp_rows)), idx + offset, t[idx],
                                    np.asarray(arrays['score_diff'], dtype=np.float32)[idx],
                                    np.asarray(arrays['remaining'], dtype=np.float32)[idx],
                                    np.asarray(arrays['overtime'], dtype=np.float32)[idx], on_1s.astype(np.float32),
                                    lab['y10'], lab['y20'], np.minimum(dt_own, 1e4), np.minimum(dt_opp, 1e4),
                                    np.full(len(idx), float(certified)), L, D, f[:, feature_names.index('ball_y')], age])
            anchor_rows.append(rows.astype(np.float32))
            feats.append(f)
        frames.append(tokens.astype(np.float16))
        elig_all.append(window_ok)
        persp_rows.append(dict(season=meta['season'], split=meta['split'], replay_id=meta['replay_id'],
                               focal_team=int(meta['focal_team']), series_id=meta['series_id'],
                               roster_id=meta.get('roster_id'), opponent_roster_id=meta.get('opponent_roster_id'),
                               region=meta.get('region'), offset=offset, length=len(t),
                               n_own_goals=len(own_t), n_opp_goals=len(opp_t), terminal_certified=bool(certified),
                               n_anchors=int(len(idx)), fps=fps))
        offset += len(t)
    if not persp_rows:
        raise ValueError(f'No perspectives in {shard}')
    name = f'risk-{path.parent.name}-{path.stem}'
    np.savez(Path(out_dir) / f'{name}.npz', frames=np.concatenate(frames), eligible=np.concatenate(elig_all),
             anchors=np.concatenate(anchor_rows) if anchor_rows else np.zeros((0, len(ANCHOR_COLUMNS)), np.float32),
             features=np.concatenate(feats) if feats else np.zeros((0, len(feature_names or [])), np.float32))
    (Path(out_dir) / f'{name}.persp.json').write_text(json.dumps(persp_rows))
    return dict(shard=str(path), chunk=f'{name}.npz', persp_file=f'{name}.persp.json', n_frames=offset,
                n_perspectives=len(persp_rows), n_anchors=int(sum(len(a) for a in anchor_rows)),
                feature_names=feature_names, seconds=time.perf_counter() - started, bytes=path.stat().st_size,
                metadata_sha256=hashlib.sha256(path.with_suffix('.parquet').read_bytes()).hexdigest())


def build(compact, out_dir, workers=8, stride=0.5):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    compact = guard_path(Path(compact)).resolve()
    pairs, audit = safe_inventory(compact)
    metadata = [m for pair in pairs for m in pair]
    shards = [s for s in sorted(audit['schema']) if Path(s).parent.name in ALLOWED_SEASONS]
    by_shard = {s: [m for m in metadata if m['_shard'] == s] for s in shards}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(process_shard, [(s, by_shard[s], str(out_dir), stride) for s in shards]))
    order = {r['shard']: r for r in results}
    manifest, persp = [], []
    frame_offset = persp_offset = anchor_offset = 0
    for s in shards:
        r = order[s]
        rows = json.loads((out_dir / r['persp_file']).read_text())
        for row in rows:
            row['offset'] += frame_offset
            row['chunk'] = r['chunk']
        persp.extend(rows)
        manifest.append(dict(r, frame_offset=frame_offset, perspective_offset=persp_offset, anchor_offset=anchor_offset))
        frame_offset += r['n_frames']
        persp_offset += r['n_perspectives']
        anchor_offset += r['n_anchors']
        (out_dir / r['persp_file']).unlink()
    perspectives = pd.DataFrame(persp)
    assert_allowed(perspectives)
    perspectives.to_parquet(out_dir / 'perspectives.parquet', index=False)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[2]).stdout.strip()
    report = dict(compact=str(compact), git_commit=commit, stride=stride, horizons=list(HORIZONS), history=HISTORY,
                  frames=frame_offset, perspectives=persp_offset, anchors=anchor_offset,
                  anchor_columns=list(ANCHOR_COLUMNS), feature_names=results[0]['feature_names'],
                  chunks=manifest, seconds=time.perf_counter() - started, test_opened=False,
                  train_seasons=list(TRAIN_SEASONS), allowed_seasons=list(ALLOWED_SEASONS),
                  terminal_certified_share=float(perspectives.terminal_certified.mean()))
    (out_dir / 'report.json').write_text(json.dumps(report, indent=1, default=str))
    return report


def load_risk(cache_dir, scratch_dir):
    cache_dir, scratch_dir = Path(cache_dir), Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads((cache_dir / 'report.json').read_text())
    frames = np.lib.format.open_memmap(scratch_dir / 'frames.npy', mode='w+', dtype=np.float16,
                                       shape=(report['frames'], 7, 16))
    eligible = np.zeros(report['frames'], dtype=bool)
    anchors, features = [], []
    started = time.perf_counter()
    for c in report['chunks']:
        with np.load(cache_dir / c['chunk'], allow_pickle=False) as z:
            o, k = c['frame_offset'], c['n_frames']
            frames[o:o + k] = z['frames']
            eligible[o:o + k] = z['eligible']
            a = z['anchors'].copy()
            a[:, ANCHOR_COLUMNS.index('perspective')] += c['perspective_offset']
            a[:, ANCHOR_COLUMNS.index('frame')] += c['frame_offset']
            anchors.append(a)
            features.append(z['features'])
    frames.flush()
    anchors = pd.DataFrame(np.concatenate(anchors), columns=ANCHOR_COLUMNS)
    features = np.concatenate(features)
    perspectives = pd.read_parquet(cache_dir / 'perspectives.parquet')
    report['load_seconds'] = time.perf_counter() - started
    return SimpleNamespace(frames=frames, eligible=eligible, anchors=anchors, features=features,
                           feature_names=report['feature_names'], perspectives=perspectives, report=report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--stride', type=float, default=0.5)
    args = parser.parse_args(argv)
    if '2026' in str(args.compact) or 'test' in Path(args.compact).resolve().parts:
        parser.error('2026/test sources are forbidden')
    report = build(args.compact, args.out, args.workers, args.stride)
    print(json.dumps({k: report[k] for k in ('frames', 'perspectives', 'anchors', 'seconds', 'terminal_certified_share')}))


if __name__ == '__main__':
    main()
