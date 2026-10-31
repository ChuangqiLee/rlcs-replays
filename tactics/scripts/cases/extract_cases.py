#!/usr/bin/env python3
"""Extract descriptive validation case windows using the project's native readers.

No network operations. Real extraction is for an operator's batch job only.
The local --self-test builds native-schema synthetic inputs under --out.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys

# Imported snapshot files must remain read-only, including bytecode caches.
sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
SEASON, SPLIT = 'rlcs-2025', 'val'
SEED, FPS, LATE, HORIZON, HALF_WINDOW = 42, 10., 60., 10., 8.
MAIN_N, APPENDIX_N = 5, 12
FIELD_X, FIELD_Y = 4096., 5120.
STRATA = ('scored', 'conceded', 'neither')


def default_repo():
    local = HERE.parent.parent / 'data' / 'repo'
    return Path(os.environ.get('RLCS_REPO', str(local if local.exists() else Path.cwd())))


def setup(repo):
    global atomic_json, clean, parsed_json, iter_frame_replays, load_state_map
    global native_index_for, build_replay_events, guard_path, extract_replay
    global last_man_arrays, valid_baseline, event_labels, FRAME_COLUMNS, GOAL_COLUMNS
    sys.path.insert(0, str(repo / 'src'))
    from tactics_code.common import atomic_json, clean
    from tactics_code.data import parsed_json, iter_frame_replays, load_state_map, FRAME_COLUMNS
    from tactics_code.events import native_index_for, build_replay_events, guard_path, GOAL_COLUMNS
    from tactics_code.extract import extract_replay
    from tactics_code.pressure import last_man_arrays
    from tactics_code.pushup_dr import valid_baseline, event_labels


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require_val(table):
    if not {'season', 'split', 'replay_id', 'series_id'} <= set(table):
        raise ValueError('Selection metadata needs season, split, replay_id, series_id')
    if not (table.season.eq(SEASON) & table.split.eq(SPLIT)).all():
        raise ValueError('Only rlcs-2025 / val metadata is permitted')
    if table.series_id.isna().any() or table.series_id.astype(str).str.strip().eq('').any():
        raise ValueError('Known source series_id is required')


def selection_inventory(compact):
    """Only the explicit validation directory; never a root-wide discovery."""
    directory = guard_path(compact / SEASON)
    if SEASON not in directory.resolve().parts:
        raise ValueError('Compact metadata directory resolves outside validation season')
    if not directory.is_dir():
        raise FileNotFoundError(f'Validation compact metadata directory missing: {directory}')
    pieces, sources = [], []
    for path in sorted(directory.glob('compact-*.parquet')):
        guard_path(path)
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Metadata symlink escapes validation directory')
        table = pd.read_parquet(path)
        require_val(table)
        pieces.append(table)
        sources.append(dict(path=str(path.resolve()), sha256=digest(path)))
    if not pieces:
        raise ValueError(f'No compact-*.parquet in {directory}')
    table = pd.concat(pieces, ignore_index=True)
    if table.groupby('replay_id').series_id.nunique().max() != 1:
        raise ValueError('Conflicting series membership')
    records = table.drop_duplicates('replay_id').sort_values('replay_id').to_dict('records')
    return records, sources


def strict_native(path, requested):
    """Preflight IDs so iter_frame_replays cannot use its read-all fallback."""
    path = guard_path(path)
    if SEASON not in path.resolve().parts:
        raise ValueError('Native frame path must reside inside rlcs-2025')
    file = pq.ParquetFile(path)
    column = file.schema_arrow.names.index('replay_id')
    ids = []
    for i in range(file.num_row_groups):
        stats = file.metadata.row_group(i).column(column).statistics
        if stats is None or not stats.has_min_max or stats.min != stats.max:
            raise ValueError('Native replay-ID statistics absent/ambiguous; refusing payload read')
        ids.append(str(stats.min))
    if len(ids) != len(set(ids)) or not set(requested) <= set(ids):
        raise ValueError('Duplicate or missing native replay row groups')
    for rid, frame in iter_frame_replays(path, selected=set(requested)):
        if not frame.replay_id.astype(str).eq(rid).all():
            raise ValueError('Replay ID payload mismatch')
        yield rid, frame


def perspectives(rows, config, counters=None):
    """Re-extract native geometry; reuse original grouping evidence from compacts."""
    by_path = defaultdict(dict)
    for row in rows:
        if row['season'] != SEASON or row['split'] != SPLIT:
            raise ValueError('Forbidden native record')
        by_path[row['_frame_path']][str(row['replay_id'])] = row
    for path, lookup in sorted(by_path.items()):
        for rid, frames in strict_native(path, lookup):
            row = lookup[rid]
            goals, certification = build_replay_events(frames, row, config)
            if counters is not None:
                counters['native_replays_seen'] += 1
            if not certification['validated']:
                if counters is not None:
                    counters['replays_failed_event_validation'] += 1
                    counters['event_failure:' + certification['failure_reason']] += 1
                continue
            goal_table = pd.DataFrame(goals, columns=GOAL_COLUMNS)
            extracted = extract_replay(frames, row, {}, {}, config, fps=FPS)
            if counters is not None:
                counters['replays_validated'] += 1
                counters['perspectives'] += len(extracted)
            for record, arrays in extracted:
                record['series_id'] = str(row['series_id'])
                record['source_frame_path'] = str(path)
                # Audited native timeline must agree with the extractor's score.
                t = arrays['time']
                score0 = np.zeros(len(t), dtype=int)
                score1 = np.zeros(len(t), dtype=int)
                for goal in goals:
                    (score0 if goal['scoring_team'] == 0 else score1)[:] += t > goal['time']
                expected = (score0 - score1) * (1 if record['focal_team'] == 0 else -1)
                known = np.isfinite(arrays['score_diff'])
                if not np.all(expected[known] == arrays['score_diff'][known]):
                    raise ValueError(f'{rid}: extracted score and audited goal timeline disagree')
                arrays.update(score_team0=score0, score_team1=score1)
                yield record, arrays, goal_table, certification


def eligibility(a):
    last = last_man_arrays(a)
    mask = (valid_baseline(a) & last['last_man_valid'] &
            (a['remaining'] > 0) & (a['remaining'] <= LATE) & (a['score_diff'] == -1))
    return mask, last


def threshold_from(factory, mode, counters):
    values = []
    for _, a, _, _ in factory(counters):
        mask, last = eligibility(a)
        counters['eligible_threshold_frames'] += int(mask.sum())
        if mask.any():
            values.append(last['last_man_y_own'][mask].astype(np.float32))
    if not values:
        raise ValueError('No eligible late trailing-by-one validation frames')
    pooled = np.concatenate(values)
    threshold = (float(np.quantile(pooled, 2 / 3, method='linear')) if mode == 'empirical'
                 else FIELD_Y * 4 / 3)
    return threshold, dict(method=mode, quantile=2 / 3, fit_split=SPLIT, fit_season=SEASON,
                          weighting='pooled eligible sampled frames; both focal perspectives',
                          count=len(pooled), minimum=float(pooled.min()), maximum=float(pooled.max()),
                          value=threshold, unit='uu from own goal line',
                          source='eligible native validation frames before outcome stratification')


def candidates_for(record, a, goals, cert, threshold, counters):
    mask, last = eligibility(a)
    t, y = a['time'], last['last_man_y_own']
    crossing = np.zeros(len(t), bool)
    crossing[1:] = (mask[:-1] & mask[1:] & (y[:-1] < threshold) & (y[1:] >= threshold) &
                    (a['segment'][:-1] == a['segment'][1:]) &
                    (np.diff(t) > 0) & (np.diff(t) <= 1.6 / FPS))
    ii = np.flatnonzero(crossing)
    counters['crossings'] += len(ii)
    labels = event_labels(t[ii], record['focal_team'], goals, cert)['y10']
    found = []
    for i, label in zip(ii, labels):
        if not np.isfinite(label):
            counters['crossings_unknown_followup'] += 1
            continue
        lo = np.searchsorted(t, t[i] - HALF_WINDOW - 1e-7)
        hi = np.searchsorted(t, t[i] + HALF_WINDOW + 1e-7, side='right')
        if (t[i] - HALF_WINDOW < t[0] - 1e-7 or t[i] + HALF_WINDOW > t[-1] + 1e-7 or
                abs(t[lo] - (t[i] - HALF_WINDOW)) > .5 / FPS or
                abs(t[hi - 1] - (t[i] + HALF_WINDOW)) > .5 / FPS):
            counters['crossings_incomplete_display'] += 1
            continue
        # Store a complete, finite seven-object display; never interpolate gaps.
        if (np.max(np.diff(t[lo:hi])) > 1.6 / FPS or
                not np.isfinite(a['players'][lo:hi, :, :2]).all() or
                not np.isfinite(a['ball'][lo:hi, :2]).all()):
            counters['crossings_missing_display_tracks'] += 1
            continue
        outcome = {0: 'neither', 1: 'scored', 2: 'conceded'}[int(label)]
        future = goals[(goals.time > t[i]) & (goals.time <= t[i] + HORIZON)]
        key = f"{record['replay_id']}:{record['focal_team']}:{a['frame'][i]}"
        found.append(dict(replay_id=record['replay_id'], series_id=record['series_id'],
                          season=record['season'], split=record['split'],
                          focal_team=int(record['focal_team']), anchor_index=int(i),
                          anchor_frame=int(a['frame'][i]), anchor_time=float(t[i]),
                          clock_at_crossing=float(a['remaining'][i]),
                          score_team0=int(a['score_team0'][i]), score_team1=int(a['score_team1'][i]),
                          last_man_slot=int(last['last_man_index'][i]),
                          previous_last_man_y_own=float(y[i - 1]), last_man_y_own=float(y[i]),
                          outcome=outcome, future_goals=future.to_dict('records'),
                          source_frame_path=record['source_frame_path'],
                          priority=hashlib.sha256(f'{SEED}:{key}'.encode()).hexdigest(),
                          observed_end_time=cert['observed_end_time'],
                          terminal_verified=cert['terminal_verified']))
        counters['candidate:' + outcome] += 1
    return found


def choose(candidates):
    """Seeded hash order, round-robin strata, globally distinct replay IDs."""
    pools = {s: sorted((c for c in candidates if c['outcome'] == s),
                      key=lambda c: (c['priority'], c['replay_id'], c['anchor_frame'])) for s in STRATA}
    # Reserve one distinct replay per main stratum using augmenting paths.
    # A simple greedy first pick could consume another stratum's only replay.
    owners, reserved = {}, {}
    def reserve(stratum, visited):
        for c in pools[stratum]:
            rid = c['replay_id']
            if rid in visited:
                continue
            visited.add(rid)
            previous = owners.get(rid)
            if previous is None or reserve(previous, visited):
                owners[rid], reserved[stratum] = stratum, c
                return True
        return False
    for stratum in STRATA:
        if not reserve(stratum, set()):
            raise ValueError('Cannot reserve distinct main replays for all outcome strata')
    chosen, used = [], set()
    for group, target in (('main', MAIN_N), ('appendix', APPENDIX_N)):
        group_rows = []
        if group == 'main':
            for s in STRATA:
                c = dict(reserved[s], figure_group=group, panel_index=len(group_rows),
                         case_id=f'{group}-{len(group_rows) + 1:02d}')
                group_rows.append(c)
                used.add(c['replay_id'])
        while len(group_rows) < target:
            progress = False
            for s in STRATA:
                available = next((c for c in pools[s] if c['replay_id'] not in used), None)
                if available is None:
                    continue
                c = dict(available, figure_group=group, panel_index=len(group_rows),
                         case_id=f'{group}-{len(group_rows) + 1:02d}')
                group_rows.append(c)
                used.add(c['replay_id'])
                progress = True
                if len(group_rows) == target:
                    break
            if not progress:
                raise ValueError(f'Insufficient distinct eligible replays for {group}; no duplicate padding')
        if group == 'main' and set(c['outcome'] for c in group_rows) != set(STRATA):
            raise ValueError('Main figure needs at least one case from every outcome stratum')
        chosen.extend(group_rows)
    return chosen


def window_table(record, a, case, synthetic):
    t = a['time']
    ii = np.flatnonzero(np.abs(t - case['anchor_time']) <= HALF_WINDOW + 1e-7)
    last = last_man_arrays(a)
    raw_ids = parsed_json(record['player_ids'], [None] * 6)
    rows = []
    for i in ii:
        base = dict(case_id=case['case_id'], figure_group=case['figure_group'],
                    panel_index=case['panel_index'], outcome=case['outcome'],
                    replay_id=record['replay_id'], series_id=record['series_id'], season=SEASON, split=SPLIT,
                    is_synthetic=synthetic, focal_team=int(record['focal_team']),
                    frame=int(a['frame'][i]), time=float(t[i]), relative_time=float(t[i] - case['anchor_time']),
                    game_clock=float(a['remaining'][i]), score_team0=int(a['score_team0'][i]),
                    score_team1=int(a['score_team1'][i]), score_diff=float(a['score_diff'][i]),
                    live=bool(a['live'][i]), segment=int(a['segment'][i]), overtime=float(a['overtime'][i]),
                    last_man_y_own=float(last['last_man_y_own'][i]),
                    anchor_time=case['anchor_time'], anchor_last_man_slot=case['last_man_slot'])
        rows.append(dict(base, entity='ball', player_slot=-1, player_id=None, team=-1, role=-1,
                         is_last_man=False, is_anchor_last_man=False,
                         x=float(a['ball'][i, 0]), y=float(a['ball'][i, 1])))
        for p in range(a['players'].shape[1]):
            own = p < len(a['roles'][i])
            rows.append(dict(base, entity=f'p{p}', player_slot=p, player_id=raw_ids[p],
                             team=int(record['focal_team'] if own else 1 - record['focal_team']),
                             role=int(a['roles'][i, p]) if own else -1,
                             is_last_man=bool(a['live'][i] and p == last['last_man_index'][i]),
                             is_anchor_last_man=p == case['last_man_slot'],
                             x=float(a['players'][i, p, 0]), y=float(a['players'][i, p, 1])))
    return pd.DataFrame(rows)


def run(rows, config, out, source, synthetic=False, tercile='empirical'):
    counters = Counter()
    factory = lambda counts=None: perspectives(rows, config, counts)
    print('Pass one: eligible validation depth distribution', flush=True)
    threshold, threshold_meta = threshold_from(factory, tercile, counters)
    print('Pass two: crossing candidates and validated follow-up', flush=True)
    candidates = []
    for record, a, goals, cert in factory():
        candidates.extend(candidates_for(record, a, goals, cert, threshold, counters))
    # The candidate table provides auditable selection, not outcome frequencies.
    atomic_json(out / 'candidate_audit.json', dict(threshold=threshold_meta, counts=counters,
                                                candidates=candidates, is_synthetic=synthetic))
    selected = choose(candidates)
    by_pair = {(c['replay_id'], c['focal_team']): c for c in selected}
    selected_rows = [r for r in rows if r['replay_id'] in {c['replay_id'] for c in selected}]
    tables = []
    print('Pass three: selected display windows', flush=True)
    for record, a, _, _ in perspectives(selected_rows, config):
        key = (record['replay_id'], record['focal_team'])
        if key in by_pair:
            tables.append(window_table(record, a, by_pair[key], synthetic))
    table = pd.concat(tables, ignore_index=True).sort_values(
        ['figure_group', 'panel_index', 'time', 'player_slot'], kind='stable').reset_index(drop=True)
    if table.case_id.nunique() != len(selected):
        raise ValueError('Selected windows disappeared on extraction pass')
    path = out / 'cases.parquet'
    table.to_parquet(path, index=False, compression='zstd')
    metadata = dict(schema_version=1, is_synthetic=synthetic, season=SEASON, split=SPLIT,
                    source=source, constants=dict(seed=SEED, fps=FPS, late_seconds=LATE,
                    outcome_seconds=HORIZON, half_window_seconds=HALF_WINDOW,
                    main_count=MAIN_N, appendix_count=APPENDIX_N, field_half_width=FIELD_X,
                    field_half_length=FIELD_Y), threshold=threshold_meta, counts=dict(counters),
                    selection_rule=dict(eligibility='Both adjacent sampled frames live, regulation, positive clock <= late_seconds, score_diff == -1, six valid tracks; known series and validated native goals',
                    crossing='previous last_man_y_own < threshold <= current last_man_y_own; same native live segment; sampled gap <= 1.6/fps',
                    outcome='First native goal in (crossing, crossing + outcome_seconds]; scored/conceded from focal perspective; neither only with known follow-up or certified terminal',
                    selection='SHA256(seed:replay_id:focal_team:anchor_frame); reserve distinct main replays for every stratum with deterministic matching, then round-robin scored/conceded/neither; globally distinct replay IDs; main then appendix; fail if insufficient',
                    display='Complete +/- half_window_seconds replay-time support at project stride; finite XY for ball and all players; preserve nonlive rows but do not plot them',
                    coordinates='Project extract_replay: focal team attacks +y; orange focal view rotates x and y by 180 degrees',
                    role='Project proximity role for focal players, -1 for opponents/ball; is_last_man is geometric min-y, independent of proximity role'),
                    selected=selected, selected_counts={g: dict(Counter(c['outcome'] for c in selected if c['figure_group'] == g)) for g in ('main', 'appendix')},
                    rows=len(table), cases=int(table.case_id.nunique()), parquet_sha256=digest(path),
                    limitations=['Outcome-stratified illustrative selection does not estimate outcome frequencies.',
                                 'Native state/goal decoding and header totals are project measurements, not manual video verification.',
                                 'Raw demolition actor IDs do not establish persistent demolition duration; project stale-track screening is used.',
                                 'Late/trailing eligibility applies at the crossing, not throughout the display window.',
                                 'Empirical tercile is descriptive validation-only pooled frame depth; it is not a training-frozen analysis threshold.',
                                 'Series may repeat across different selected replays. No independent-series inference is made.'])
    atomic_json(out / 'cases_meta.json', metadata)
    return table, metadata, candidates


def synthetic_inputs(out, config):
    """Build actual native-schema parquet/index fixtures, including orange views."""
    directory = out / 'synthetic_inputs' / 'frames' / 'fps30' / SEASON
    directory.mkdir(parents=True, exist_ok=True)
    frames_list, index_rows, selection = [], [], []
    native_fps = FPS * 3
    t = np.arange(int(42 * native_fps) + 1) / native_fps
    for j in range((MAIN_N + APPENDIX_N + len(STRATA) - 1) // len(STRATA) + 2):
        for outcome in STRATA:
            focal = j % 2
            sign = 1 if focal == 0 else -1
            rid = f'SYNTHETIC-{outcome}-{j:02d}'
            sid = f'SYNTHETIC-series-{outcome}-{j:02d}'
            df = pd.DataFrame(0., index=np.arange(len(t)), columns=[c for c in FRAME_COLUMNS if c != 'replay_id'])
            df['replay_id'], df['frame'], df['current time'] = rid, np.arange(len(t)), t
            df['frame time'], df['seconds remaining'] = 1 / native_fps, 75 - t
            df['game state'], df['ball has been hit'] = 7., 1.
            depth_y = -1800 + 4000 * np.sin((t - 14) / 7)
            df['Ball - position x'] = sign * (1100 * np.sin(t / 3 + j / 5))
            df['Ball - position y'] = sign * np.clip(depth_y + 1300, -4300, 4500)
            df['Ball - position z'] = 120 + 40 * np.cos(t)
            players = []
            for p in range(6):
                team = p // 3
                own = team == focal
                slot = p % 3
                x = (slot - 1) * 1800 + 220 * np.sin(t / 2 + slot + j / 3)
                y = depth_y + slot * 450 if own else 3400 + 400 * np.sin(t / 3 + slot)
                for axis, values in zip('xyz', (sign * x, sign * y, 30 + 10 * np.sin(t + slot))):
                    df[f'p{p} - position {axis}'] = values
                    df[f'p{p} - linear velocity {axis}'] = np.gradient(values, t)
                df[f'p{p} - boost level (raw replay units)'] = 150 + 20 * np.sin(t + p)
                players.append(dict(team=team, remote_id={'synthetic': f'{rid}-p{p}'}))
            events = [(4., 1 - focal)]
            if outcome != 'neither':
                events.append((27., focal if outcome == 'scored' else 1 - focal))
            for when, team in events:
                k = int(round(when * native_fps))
                df.loc[k:k + int(native_fps) - 1, 'game state'] = 8.
                df.loc[k:k + int(native_fps) - 1, 'ball has been hit'] = 0.
                df.loc[k - 1, 'Ball - position y'] = FIELD_Y + 80 if team == 0 else -FIELD_Y - 80
            for axis in 'xyz':
                df[f'Ball - linear velocity {axis}'] = np.gradient(df[f'Ball - position {axis}'], t)
            totals = [sum(team == q for _, team in events) for q in (0, 1)]
            header = {name: [dict(stats={'Goals': total})] for name, total in zip(('team_zero', 'team_one'), totals)}
            row = dict(replay_id=rid, season=SEASON, status='ok', n_players=len(players),
                       players=json.dumps(players), replay_meta=json.dumps(header), fps=native_fps)
            frames_list.append(df[FRAME_COLUMNS])
            index_rows.append(row)
            selection.append(dict(replay_id=rid, season=SEASON, split=SPLIT, series_id=sid))
    path = directory / 'synthetic.parquet'
    with pq.ParquetWriter(path, pa.Table.from_pandas(frames_list[0], preserve_index=False).schema) as writer:
        for frame in frames_list:
            writer.write_table(pa.Table.from_pandas(frame, preserve_index=False), row_group_size=len(frame))
    pd.DataFrame(index_rows).to_parquet(directory / 'synthetic.index.parquet', index=False)
    compact = out / 'synthetic_inputs' / 'compact'
    (compact / SEASON).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(selection).to_parquet(compact / SEASON / 'compact-synthetic.parquet', index=False)
    return compact, out / 'synthetic_inputs'


def self_tests(table, meta, candidates, rows, config, out):
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    picked = meta['selected']
    check('required_panel_counts', table[table.figure_group == 'main'].case_id.nunique() == MAIN_N and
          table[table.figure_group == 'appendix'].case_id.nunique() == APPENDIX_N)
    check('all_main_strata', set(meta['selected_counts']['main']) == set(STRATA))
    check('distinct_replays', len({c['replay_id'] for c in picked}) == MAIN_N + APPENDIX_N)
    check('order_independent_seeded_selection', choose(candidates[::-1]) == picked)
    overlap = [dict(c, outcome='scored') for c in candidates]
    rare = min(overlap, key=lambda c: c['priority'])
    other = next(c for c in overlap if c['replay_id'] != rare['replay_id'])
    overlap += [dict(rare, outcome='conceded'), dict(other, outcome='neither')]
    check('reserve_rare_overlapping_stratum', {c['outcome'] for c in choose(overlap) if c['figure_group'] == 'main'} == set(STRATA))
    check('seven_entities_per_frame', table.groupby(['case_id', 'frame']).size().eq(7).all())
    check('full_window_at_requested_rate', table.groupby('case_id').frame.nunique().eq(round(2 * HALF_WINDOW * FPS) + 1).all())
    check('relative_time_endpoints', np.allclose(table.groupby('case_id').relative_time.min(), -HALF_WINDOW) and
          np.allclose(table.groupby('case_id').relative_time.max(), HALF_WINDOW))
    check('synthetic_provenance', table.is_synthetic.all() and meta['is_synthetic'])
    check('val_only', table.season.eq(SEASON).all() and table.split.eq(SPLIT).all())
    anchors = table[np.abs(table.relative_time) < 1e-7]
    check('late_trailing_live_anchors', anchors.live.all() and anchors.score_diff.eq(-1).all() and
          anchors.game_clock.between(np.nextafter(0., 1.), LATE).all())
    check('geometric_last_man_at_anchor', anchors.groupby('case_id').is_last_man.sum().eq(1).all())
    check('crossing_brackets_threshold', all(c['previous_last_man_y_own'] < meta['threshold']['value'] <= c['last_man_y_own'] for c in picked))
    check('constructed_outcomes', all(f"-{c['outcome']}-" in c['replay_id'] for c in picked))
    examples = list(perspectives(rows[:1], config))
    a0, a1 = examples[0][1], examples[1][1]
    check('orange_rotation_xy', np.allclose(a0['ball'][:, :2], -a1['ball'][:, :2]) and
          np.allclose(a0['players'][:, :3, :2], -a1['players'][:, 3:, :2]))
    record, arrays, goals, cert = examples[0]
    threshold = meta['threshold']['value']
    record = dict(record)
    for change in ('unknown_score', 'overtime', 'nonlive'):
        bad = {k: v.copy() for k, v in arrays.items()}
        if change == 'unknown_score': bad['score_diff'][:] = np.nan
        if change == 'overtime': bad['overtime'][:] = 1
        if change == 'nonlive': bad['live'][:] = False
        check('exclude_' + change, not candidates_for(record, bad, goals, cert, threshold, Counter()))
    bad = {k: v.copy() for k, v in arrays.items()}
    bad['segment'] = np.arange(len(bad['time']))
    check('no_crossing_across_segment_reset', not candidates_for(record, bad, goals, cert, threshold, Counter()))
    empty_goals = goals.iloc[:0]
    truncated = dict(cert, observed_end_time=6., terminal_verified=False)
    check('truncation_is_unknown', np.isnan(event_labels(np.array([5.]), 0, empty_goals, truncated)['y10'][0]))
    gapped = dict(cert, gap_start_times=json.dumps([5.5]), gap_end_times=json.dumps([6.5]))
    check('followup_gap_is_unknown', np.isnan(event_labels(np.array([5.]), 0, empty_goals, gapped)['y10'][0]))
    for name, callback in (
            ('test_path_guard', lambda: guard_path(out / 'rlcs-2026' / 'never-open.parquet')),
            ('split_guard', lambda: require_val(pd.DataFrame([dict(season=SEASON, split='test', replay_id='x', series_id='s')]))),
            ('insufficient_stratum_fails', lambda: choose([c for c in candidates if c['outcome'] != 'conceded']))):
        try: callback()
        except ValueError: checks.append(name)
        else: raise AssertionError(name)
    # No replay-ID statistics must be rejected before any frame payload is read.
    badpath = out / 'synthetic_inputs' / 'frames' / 'fps30' / SEASON / 'missing-stats.parquet'
    pd.DataFrame({'replay_id': ['blocked']}).to_parquet(badpath, index=False, write_statistics=False)
    try: list(strict_native(badpath, {'blocked'}))
    except ValueError: checks.append('missing_statistics_fails_closed')
    else: raise AssertionError('missing_statistics_fails_closed')
    atomic_json(out / 'self_test_report.json', dict(status='passed', checks=checks, count=len(checks),
                rows=len(table), selected_cases=len(picked), source='synthetic_inputs built by extract_cases.py'))
    print(f'SELF-TEST PASSED: {len(checks)} checks; {len(picked)} cases; {len(table)} rows', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repo', type=Path, default=default_repo())
    parser.add_argument('--compact', type=Path, help='Project compact ROOT; only its rlcs-2025 metadata is opened')
    parser.add_argument('--data-root', type=Path, help='Native data root containing frames/fps30/rlcs-2025')
    parser.add_argument('--state-map', type=Path, help='Reviewed project state_map_rlcs.json')
    parser.add_argument('--tercile', choices=('empirical', 'field'), default='empirical')
    args = parser.parse_args()
    args.repo, args.out = args.repo.resolve(), args.out.resolve()
    if args.out == args.repo or args.out.is_relative_to(args.repo):
        parser.error('--out must be outside the read-only repository')
    args.out.mkdir(parents=True, exist_ok=True)
    setup(args.repo)
    if args.self_test:
        # Configuration is copied from the snapshot artifact, not guessed.
        config_path = args.repo / 'results' / 'extract.json'
        artifact = json.loads(config_path.read_text())
        config = artifact['details']['state_map'] if 'details' in artifact else artifact['state_map']
        compact, data_root = synthetic_inputs(args.out, config)
    else:
        if not all((args.compact, args.data_root, args.state_map)):
            parser.error('Real extraction requires explicit --compact, --data-root and --state-map')
        compact, data_root = guard_path(args.compact), guard_path(args.data_root)
        config_path = guard_path(args.state_map)
        config = load_state_map(config_path)
    records, sources = selection_inventory(compact)
    # native_index_for scans only this season. Check its paths before it opens
    # any index, including symlinks that otherwise could point into training.
    native_root = Path(data_root) / 'frames' / 'fps30'
    if not native_root.exists():
        native_root = Path(data_root)
    native_directory = guard_path(native_root / SEASON)
    if SEASON not in native_directory.resolve().parts:
        raise ValueError('Native directory resolves outside validation season')
    for path in native_directory.glob('*.index.parquet'):
        guard_path(path)
        if not path.resolve().is_relative_to(native_directory.resolve()):
            raise ValueError('Native index symlink escapes validation directory')
    rows = native_index_for(records, data_root)
    for row in rows:
        if row['status'] != 'ok' or row['n_players'] != 6:
            raise ValueError('Selected native replay is not an eligible parsed six-player game')
    source = dict(kind='synthetic native-schema fixtures' if args.self_test else 'real validation native frames',
                  repo=str(args.repo), data_root=str(Path(data_root).resolve()), selection_metadata=sources,
                  state_map=dict(path=str(config_path), sha256=digest(config_path), config=config),
                  imported_code={name: digest(args.repo / 'src' / 'tactics_code' / name) for name in
                                 ('data.py', 'extract.py', 'pressure.py', 'events.py', 'pushup_dr.py')},
                  script_sha256=digest(__file__), index_files=[dict(path=p, sha256=digest(p)) for p in sorted({
                      str(Path(r['_frame_path']).with_name(Path(r['_frame_path']).stem + '.index.parquet')) for r in rows})])
    table, meta, candidates = run(rows, config, args.out, source, args.self_test, args.tercile)
    if args.self_test:
        self_tests(table, meta, candidates, rows, config, args.out)
    else:
        print(json.dumps(dict(status='complete', cases=meta['cases'], rows=meta['rows'], out=str(args.out))))


if __name__ == '__main__':
    main()
