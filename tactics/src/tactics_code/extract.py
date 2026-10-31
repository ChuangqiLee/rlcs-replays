"""Extract compact focal-team arrays without inventing parser semantics."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .common import Run, add_common_args, atomic_json, split_for_season
from .data import (BALL_COLUMNS, DEFAULT_DATA_ROOT, FLAG_COLUMNS, PLAYER_COLUMNS, decode_replay_states, frame_goals,
                   frame_overtime, group_metadata, iter_frame_replays, load_manifest, load_state_map,
                   parsed_json, raw_path_lookup, read_index, roster_key, stable_player_id, timed_goals)


def role_ranks(player_position, ball_position, time, live, margin=100., hold=.3):
    """Proximity ranks with sustained adjacent challenges; absent players stay -1."""
    n = len(time)
    ranks = np.full((n, 3), -1, np.int8)
    uncertain = np.ones(n, bool)
    order, pending = None, {}
    distances = np.linalg.norm(player_position - ball_position[:, None, :], axis=-1)
    for i in range(n):
        valid = np.isfinite(distances[i])
        if not live[i] or not np.isfinite(time[i]):
            order, pending = None, {}
            continue
        current = list(np.flatnonzero(valid))
        if order is None or set(order) != set(current):
            order = sorted(current, key=lambda p: (distances[i, p], p))
            pending = {}
        for j in range(max(0, len(order) - 1)):
            incumbent, challenger = order[j:j + 2]
            pair = (incumbent, challenger)
            if distances[i, challenger] < distances[i, incumbent] and distances[i, challenger] + margin <= distances[i, incumbent]:
                pending.setdefault(pair, float(time[i]))
                if time[i] - pending[pair] + 1e-7 >= hold:
                    order[j:j + 2] = [challenger, incumbent]
                    pending.clear()
            else:
                pending.pop(pair, None)
        for rank, player in enumerate(order):
            ranks[i, player] = rank
        sorted_d = np.sort(distances[i, valid])
        uncertain[i] = len(current) != 3 or bool(np.any(np.diff(sorted_d) < margin))
    return ranks, uncertain


def candidate_touches(ball, players, time, hit, live, radius=250., impulse=150., dedup=.15):
    """Conservative 30 Hz contacts, not guaranteed touches or possession.

    The hit flag is a kickoff latch, never a per-touch event. Require proximity,
    a local distance minimum, a velocity impulse, one unambiguous car, and no
    nearby arena surface. This intentionally omits many real wall/floor touches.
    """
    out = np.full(len(time), -1, np.int8)
    if len(time) < 5:
        return out
    dist = np.linalg.norm(players[:, :, :3] - ball[:, None, :3], axis=2)
    jump = np.linalg.norm(np.diff(ball[:, 3:6], axis=0, prepend=ball[:1, 3:6]), axis=1)
    last = -np.inf
    for i in range(2, len(time) - 2):
        if not live[i] or not (hit[i] > 0) or not np.isfinite(time[i]) or time[i] - last < dedup:
            continue
        x, y, z = ball[i, :3]
        if not np.isfinite([x, y, z]).all() or abs(x) > 4096 - 300 or abs(y) > 5120 - 300 or z < 200 or z > 2044 - 300:
            continue
        nearest = np.flatnonzero(np.isfinite(dist[i]) & (dist[i] <= radius))
        if len(nearest) != 1:
            continue
        player = int(nearest[0])
        neighborhood = dist[i - 2:i + 3, player]
        if not np.isfinite(neighborhood).all() or dist[i, player] > neighborhood.min() + 1e-5:
            continue
        if np.nanmax(jump[i - 2:i + 3]) < impulse:
            continue
        out[i], last = player, time[i]
    return out


def live_and_context(df, meta, config, heuristic=False, decoded=None):
    time = df['current time'].to_numpy(dtype=float)
    frame = df['frame'].to_numpy(dtype=float)
    remaining = df['seconds remaining'].to_numpy(dtype=float)
    state = df['game state'].to_numpy(dtype=float)
    hit = df['ball has been hit'].to_numpy(dtype=float)
    if config.get('state_decoding') == 'per_replay_decoded':
        decoded = decode_replay_states(df) if decoded is None else decoded
        live = decoded['live'].copy()
        provenance = 'explicit_state_map'
    elif config.get('live_states') is not None:
        live = np.isin(state, config['live_states'])
        provenance = 'explicit_state_map'
    elif heuristic:
        # Positive running regulation clock + a latched kickoff hit is only a
        # conservative exploratory subset. Zero-second play and OT remain unknown.
        delta = np.diff(remaining, prepend=np.nan)
        live = (remaining > 0) & (delta < 0) & (delta > -1) & (hit > 0)
        provenance = 'exploratory_clock_hit_heuristic'
    else:
        raise ValueError('Supply --state-map/--live-states or explicitly opt into --allow-heuristic-live')
    exclude = config.get('kickoff_states', []) + config.get('goal_replay_states', [])
    if decoded is None:
        live &= ~np.isin(state, exclude)
    live &= np.isfinite(time) & np.isfinite(frame)
    live &= np.isfinite(df[BALL_COLUMNS[:3]].to_numpy()).all(axis=1)
    overtime = np.full(len(df), np.nan, np.float32)
    if 'regulation_states' in config:
        overtime[np.isin(state, config['regulation_states'])] = 0
    if 'overtime_states' in config:
        overtime[np.isin(state, config['overtime_states'])] = 1
    if config.get('overtime_detection') == 'frame_state_transitions':
        overtime = frame_overtime(df, config, decoded)
    elif heuristic and provenance != 'explicit_state_map' and 'regulation_states' not in config:
        # Positive *decreasing* clocks are the only provisionally identified regulation subset.
        overtime[live] = 0
    score = np.full(len(df), np.nan, np.float32)
    goals, goal_status = timed_goals(meta, config)
    if goals is None:
        goals, _ = frame_goals(df, config, decoded)
        if goals is not None:
            goal_status = 'frame_state_transitions'
    boundaries = np.zeros(len(df), bool)
    if goals is not None:
        score[:] = 0
        for value, team, unit in goals:
            clock = frame if unit == 'frame' else time
            if team is None:
                # The event time is known, but every later score is unknown.
                score[clock > value] = np.nan
            else:
                score += (clock > value) * (1 if team == 0 else -1)
            # Prevent windows crossing a goal even if state decoding is incomplete.
            goal_index = np.searchsorted(clock, value, side='left')
            if goal_index < len(df):
                boundaries[goal_index] = True
                live[goal_index] = False
    return live, overtime, score, provenance, goal_status, boundaries


def segment_ids(live, time, frame, fps):
    out = np.full(len(live), -1, np.int32)
    current = -1
    for i in range(len(live)):
        if not live[i]:
            continue
        new = (i == 0 or not live[i - 1] or time[i] <= time[i - 1]
               or time[i] - time[i - 1] > 1.75 / fps or frame[i] <= frame[i - 1])
        if new:
            current += 1
        out[i] = current
    return out


def extract_replay(df, row, manifest, raw_paths, config, fps=10., margin=100., hold=.3,
                   heuristic=False, touch_radius=250., touch_impulse=150.):
    native_fps = float(row.get('fps', 30))
    ratio = native_fps / fps
    if fps <= 0 or ratio < 1 or not math.isclose(ratio, round(ratio), abs_tol=1e-7):
        raise ValueError(f'--fps {fps} must divide native fps {native_fps}; expected 5/10/15/30 for 30 Hz')
    stride = int(round(ratio))
    df = df.sort_values('frame', kind='stable').reset_index(drop=True)
    if df['frame'].duplicated().any():
        raise ValueError(f"{row['replay_id']}: duplicate frame identifiers")
    if len(df) < 2:
        return []
    raw_players = parsed_json(row.get('players'), [])
    if len(raw_players) != 6 or sorted(p.get('team') for p in raw_players) != [0, 0, 0, 1, 1, 1]:
        return []
    meta = parsed_json(row.get('replay_meta'), {})
    time = df['current time'].to_numpy(dtype=float)
    frame = df['frame'].to_numpy(dtype=float)
    if np.any(np.diff(time[np.isfinite(time)]) <= 0):
        raise ValueError(f"{row['replay_id']}: current-time clock is not strictly increasing; audit parser semantics")
    ball = df[BALL_COLUMNS].to_numpy(dtype=np.float32)
    players = np.stack([df[cols].to_numpy(dtype=np.float32) for cols in PLAYER_COLUMNS], axis=1)
    flags = np.stack([df[cols].to_numpy(dtype=np.float32) for cols in FLAG_COLUMNS], axis=1)
    decoded = decode_replay_states(df) if config.get('state_decoding') == 'per_replay_decoded' else None
    live, overtime, score, state_source, goal_source, _ = live_and_context(df, meta, config, heuristic, decoded)
    native_segments = segment_ids(live, time, frame, native_fps)
    touches = candidate_touches(ball, players, time, df['ball has been hit'].to_numpy(float), live,
                                radius=touch_radius, impulse=touch_impulse)
    chosen = np.arange(0, len(df), stride)
    # Do not silently bridge a native reset that lands between retained frames.
    sampled_live = live[chosen].copy()
    sampled_segment = native_segments[chosen]
    sampled_touches = np.full(len(chosen), -1, np.int8)
    for i, stop_frame in enumerate(chosen):
        begin = 0 if i == 0 else chosen[i - 1] + 1
        stop = stop_frame + 1
        events = touches[begin:stop]
        events = events[events >= 0]
        if len(events) == 1 and np.all(native_segments[begin:stop] == native_segments[stop_frame]):
            sampled_touches[i] = events[0]
    # A demolition actor value is not necessarily a persistent demolition state.
    # Keep raw values and expose decoded states only when a user supplies sentinels.
    demolished_raw = players[:, :, 7].copy()
    absent_values = config.get('demolition_absent_values', [config['demolition_sentinel']] if 'demolition_sentinel' in config else None)
    if absent_values is not None:
        known = np.isfinite(demolished_raw)
        players[:, :, 7] = np.where(known, ~np.isin(demolished_raw, absent_values), np.nan)
        demo_source = 'explicit_sentinel_decode_indicator_not_validated_duration'
    else:
        players[:, :, 7] = np.nan
        demo_source = 'unknown_raw_saved_separately'
    groups = group_metadata(row, manifest, raw_paths)
    results = []
    for team in (0, 1):
        own = [i for i, p in enumerate(raw_players) if p['team'] == team]
        other = [i for i, p in enumerate(raw_players) if p['team'] != team]
        order = own + other
        b, p = ball[chosen].copy(), players[chosen][:, order].copy()
        if team == 1:
            b[:, [0, 1, 3, 4]] *= -1
            p[:, :, [0, 1, 3, 4]] *= -1
        remapped = np.full(len(chosen), -1, np.int8)
        for canonical, original in enumerate(order):
            remapped[sampled_touches == original] = canonical
        ranks = np.full((len(chosen), 3), -1, np.int8)
        uncertainty = np.ones(len(chosen), bool)
        role_positions = p[:, :3, :3].copy()
        # A decoded demolition can retain stale finite coordinates in the parser.
        # Exclude it from role assignment while preserving raw compact geometry.
        role_positions[p[:, :3, 7] == 1] = np.nan
        # Reset hysteresis at all native live-segment boundaries, including subsampled interruptions.
        for segment in np.unique(sampled_segment[sampled_segment >= 0]):
            mask = sampled_segment == segment
            ranks[mask], uncertainty[mask] = role_ranks(role_positions[mask], b[mask, :3], time[chosen][mask],
                                                      sampled_live[mask], margin, hold)
        arrays = dict(ball=b, players=p, flags=flags[chosen][:, order], roles=ranks,
                      role_uncertain=uncertainty, touch=remapped, time=time[chosen],
                      frame=frame[chosen].astype(np.int64), remaining=df['seconds remaining'].to_numpy(np.float32)[chosen],
                      score_diff=score[chosen] * (1 if team == 0 else -1), overtime=overtime[chosen],
                      live=sampled_live, segment=sampled_segment,
                      game_state=df['game state'].to_numpy(np.float32)[chosen],
                      ball_has_been_hit=df['ball has been hit'].to_numpy(np.float32)[chosen],
                      demolished_raw=demolished_raw[chosen][:, order])
        ids = [stable_player_id(raw_players[i]) for i in order]
        record = dict(replay_id=str(row['replay_id']), season=str(row['season']), split=split_for_season(row['season']),
                      focal_team=team, player_ids=json.dumps(ids), roster_id=roster_key(ids[:3]),
                      team_id=None, opponent_roster_id=roster_key(ids[3:]), fps=fps, native_fps=native_fps,
                      state_source=state_source, score_source=goal_source, demolition_source=demo_source,
                      **groups)
        if decoded is not None:
            record.update(state_decoding='per_replay_decoded',
                          state_decoding_details=json.dumps(decoded['diagnostics']))
        results.append((record, arrays))
    return results


def _write_task(task):
    records, manifest, raw_paths, config, options, target = task
    chunks, metadata, offset = {}, [], 0
    by_path = {}
    for row in records:
        by_path.setdefault(row['_frame_path'], {})[str(row['replay_id'])] = row
    seen, reasons = set(), {}
    for path, lookup in by_path.items():
        for rid, frame in iter_frame_replays(Path(path), set(lookup)):
            if rid in seen:
                raise ValueError(f'{rid}: replay appears in multiple frame row groups; refusing truncated/duplicated extraction')
            seen.add(rid)
            extracted = extract_replay(frame, lookup[rid], manifest, raw_paths, config, **options)
            if not extracted:
                reasons['invalid_team_roster_or_short'] = reasons.get('invalid_team_roster_or_short', 0) + 1
            for record, arrays in extracted:
                n = len(arrays['time'])
                record.update(start=offset, stop=offset + n)
                offset += n
                metadata.append(record)
                for key, value in arrays.items():
                    chunks.setdefault(key, []).append(value)
    missing = set(str(row['replay_id']) for row in records) - seen
    if missing:
        raise ValueError(f'Index references {len(missing)} missing frame row groups: {sorted(missing)[:3]}')
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if metadata:
        temp = target.with_suffix('.tmp.npz')
        np.savez_compressed(temp, **{k: np.concatenate(v, axis=0) for k, v in chunks.items()})
        os.replace(temp, target)
        temp_meta = target.with_suffix('.tmp.parquet')
        pd.DataFrame(metadata).to_parquet(temp_meta, index=False)
        os.replace(temp_meta, target.with_suffix('.parquet'))
    return dict(replays=len(seen), perspectives=len(metadata), frames=offset, reasons=reasons, shard=str(target),
                live_frames=int(sum(np.count_nonzero(a) for a in chunks.get('live', []))))


def select_replays(index, max_replays, seed, manifest=None, raw_paths=None):
    """Outcome-independent, deterministic, complete-known-series sample per season.

    A series is skipped when it cannot fit the remaining cap. Unknown memberships
    can only be sampled as feasibility replays and remain ineligible for grouped
    inference. Identical inputs/seed select identical IDs regardless of row order.
    """
    eligible = index[(index['status'] == 'ok') & (index['n_players'] == 6)].copy()
    if eligible['replay_id'].duplicated().any():
        raise ValueError('Duplicate replay IDs in eligible indexes; resolve before extraction')
    if max_replays is not None and max_replays < 1:
        raise ValueError('--max-replays must be positive')
    manifest, raw_paths = manifest or {}, raw_paths or {}
    eligible['_sample_group'] = [group_metadata(row, manifest, raw_paths)['series_id'] or ('unknown:' + str(row['replay_id']))
                                  for row in eligible.to_dict('records')]
    kept = []
    for _, season in eligible.groupby('season', sort=True):
        groups = list(season.groupby('_sample_group', sort=True))
        groups.sort(key=lambda pair: hashlib.sha256(f'{seed}:{pair[0]}'.encode()).hexdigest())
        count = 0
        for _, group in groups:
            if max_replays is not None and count + len(group) > max_replays:
                continue
            kept.append(group.sort_values('replay_id'))
            count += len(group)
    return (pd.concat(kept) if kept else eligible.iloc[:0]).drop(columns='_sample_group')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--compact', type=Path, help='Default: OUTPUT/compact')
    parser.add_argument('--state-map', type=Path, help='Explicit parser map (default: ./state_map_rlcs.json)')
    parser.add_argument('--live-states', help='Comma-separated audited numeric state values; OT needs --state-map')
    parser.add_argument('--allow-heuristic-live', action='store_true', help='Exploratory only: positive decreasing clock and hit latch')
    parser.add_argument('--max-replays', type=int, help='Per-season cap; deterministic whole-known-series sample')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--shard-replays', type=int, default=250)
    parser.add_argument('--rank-margin', type=float, default=100.)
    parser.add_argument('--rank-hold', type=float, default=.3)
    parser.add_argument('--touch-radius', type=float, default=250.)
    parser.add_argument('--touch-impulse', type=float, default=150.)
    args = parser.parse_args(argv)
    with Run(args, 'extract', method='Audited compact extraction') as run:
        # Explicit exploratory/live-only modes retain their previous behavior.
        config = (load_state_map(args.state_map) if args.state_map or not (args.live_states or args.allow_heuristic_live)
                  else {})
        if args.live_states:
            config.pop('state_decoding', None)
            config['live_states'] = [float(x) for x in args.live_states.split(',')]
        if (config.get('live_states') is None and config.get('state_decoding') != 'per_replay_decoded'
                and not args.allow_heuristic_live):
            raise ValueError('Unknown game-state codes: pass audited --state-map/--live-states, or exploratory --allow-heuristic-live')
        if args.workers < 1 or args.shard_replays < 1 or args.rank_margin < 0 or args.rank_hold < 0:
            raise ValueError('workers/shard-replays must be positive; hysteresis thresholds nonnegative')
        output = args.compact or args.output / 'compact'
        index = read_index(args.data_root)
        manifest, conflicts = load_manifest(args.data_root)
        raw_paths = raw_path_lookup(args.data_root)
        selected = select_replays(index, args.max_replays, args.seed, manifest, raw_paths)
        if conflicts:
            raise ValueError(f'{len(conflicts)} conflicting manifest memberships; resolve before grouped analysis')
        options = dict(fps=args.fps, margin=args.rank_margin, hold=args.rank_hold, heuristic=args.allow_heuristic_live,
                       touch_radius=args.touch_radius, touch_impulse=args.touch_impulse)
        tasks = []
        for season, group in selected.groupby('season', sort=True):
            # Selection is fixed above; physical packing follows source shards to
            # avoid reopening hundreds of parquet footers for every worker task.
            rows = group.sort_values(['_frame_path', 'replay_id']).to_dict('records')
            for number, start in enumerate(range(0, len(rows), args.shard_replays)):
                subset = rows[start:start + args.shard_replays]
                ids = {r['replay_id'] for r in subset}
                tasks.append((subset, {k: v for k, v in manifest.items() if k in ids},
                              {k: v for k, v in raw_paths.items() if k in ids}, config, options,
                              str(output / str(season) / f'compact-{number:04d}.npz')))
        if any(output.rglob('*.npz')):
            raise FileExistsError(f'{output}: compact shards exist; use a new directory to avoid mixing configurations')
        run.idea('p3-extraction', 'Audited 3v3 extraction', 'running', motivation='Native event extraction and compact focal-team arrays')
        summaries = []
        if args.workers == 1:
            for task in tasks:
                summary = _write_task(task)
                summaries.append(summary)
                run.metric(replays=sum(s['replays'] for s in summaries), frames=sum(s['frames'] for s in summaries))
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(_write_task, task) for task in tasks]
                for future in as_completed(futures):
                    summaries.append(future.result())
                    run.metric(replays=sum(s['replays'] for s in summaries), frames=sum(s['frames'] for s in summaries))
        summary = dict(replays=sum(s['replays'] for s in summaries), perspectives=sum(s['perspectives'] for s in summaries),
                       frames=sum(s['frames'] for s in summaries), live_frames=sum(s['live_frames'] for s in summaries), shards=len(summaries))
        details = dict(shards=summaries, state_map=config, options=options, max_replays_per_season=args.max_replays,
                       selected_by_season=selected.groupby('season').size().to_dict(),
                       limitations=['Rank is proximity role, not tactical ground truth.',
                                    'Raw demolition indicators retained; unknown decoded states are NaN.',
                                    'No organization IDs are inferred from names or rosters.',
                                    'Candidate touches are conservative and not possession.',
                                    'Caps preserve whole known eligible series; unknown memberships remain feasibility-only.'])
        atomic_json(output / 'extraction.json', {'metrics': summary, **details})
        run.result('extract', summary, notes='NaN context stays unknown; no frame-wise complete-case mode filter.', details=details)
        run.idea('p3-extraction', 'Audited 3v3 extraction', 'promising' if summary['live_frames'] else 'pruned',
                 prune_reason='' if summary['live_frames'] else 'No audited/eligible live frames')


if __name__ == '__main__':
    main()
