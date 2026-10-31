"""Audit actual replay indexes, grouping coverage and native frame conventions."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .common import Run, add_common_args
from .data import (BALL_COLUMNS, DEFAULT_DATA_ROOT, frame_goals, goal_agreement, goal_totals,
                   group_metadata, iter_frame_replays, load_manifest, load_state_map, parsed_json,
                   raw_path_lookup, read_index, stable_player_id, timed_goals)


def _goal_fields(value, path=''):
    fields = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f'{path}.{key}' if path else key
            if 'goal' in key.lower():
                fields.append((here, type(item).__name__))
            if isinstance(item, dict):
                fields.extend(_goal_fields(item, here))
            elif isinstance(item, list) and item and isinstance(item[0], dict):
                fields.extend(_goal_fields(item[0], here + '[]'))
    return fields


def _range_update(store, name, values):
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    entry = store.setdefault(name, {'count': 0, 'finite': 0, 'missing': 0, 'min': None, 'max': None})
    entry['count'] += int(values.size)
    entry['finite'] += int(finite.sum())
    entry['missing'] += int((~finite).sum())
    if finite.any():
        lo, hi = float(values[finite].min()), float(values[finite].max())
        entry['min'] = lo if entry['min'] is None else min(entry['min'], lo)
        entry['max'] = hi if entry['max'] is None else max(entry['max'], hi)


def audit(root: Path, run=None, max_replays=None, seed=42, state_map=None):
    import pyarrow.parquet as pq
    state_map = load_state_map() if state_map is None else state_map
    index = read_index(root)
    manifest, conflicts = load_manifest(root)
    raw_paths = raw_path_lookup(root)
    duplicate_ids = sorted(index.loc[index['replay_id'].duplicated(keep=False), 'replay_id'].unique().tolist())
    counts = index.groupby(['season', 'status', 'n_players'], dropna=False).size().reset_index(name='games').to_dict('records')
    ok = index[index['status'] == 'ok']
    nplayers = pd.to_numeric(ok['n_players'], errors='coerce')
    odd = int(((nplayers % 2) == 1).sum())
    modes = {name: int((nplayers == n).sum()) for name, n in [('1v1', 2), ('2v2', 4), ('3v3', 6)]}
    mode_total = sum(modes.values())
    meta_counts, grouping = Counter(), Counter()
    per_season = defaultdict(Counter)
    goal_fields, root_keys = Counter(), Counter()
    unavailable_examples, metadata_errors = [], []
    stable_ids = defaultdict(set)
    for row in index.to_dict('records'):
        rid = str(row['replay_id'])
        group = group_metadata(row, manifest, raw_paths)
        source = group['series_source'] or 'missing'
        grouping[source] += 1
        per_season[row['season']][source] += 1
        if group['series_id'] is None and len(unavailable_examples) < 20:
            unavailable_examples.append(rid)
        players = parsed_json(row.get('players'), None)
        meta = parsed_json(row.get('replay_meta'), None)
        if not isinstance(players, list) or not isinstance(meta, dict):
            metadata_errors.append(rid)
            continue
        root_keys.update(meta.keys())
        goal_fields.update(f'{field} ({kind})' for field, kind in _goal_fields(meta))
        ids = [stable_player_id(p) for p in players]
        meta_counts['players_total'] += len(ids)
        meta_counts['stable_player_ids'] += sum(x is not None for x in ids)
        meta_counts['all_player_ids_available'] += bool(ids) and all(x is not None for x in ids)
        meta_counts['team_slot_labels_available'] += bool(players) and all(p.get('team') in (0, 1) for p in players)
        meta_counts['valid_3v3_roster'] += len(players) == 6 and sorted(p.get('team', -1) for p in players) == [0, 0, 0, 1, 1, 1]
        for player, pid in zip(players, ids):
            if pid:
                stable_ids[pid].add(player.get('name', ''))
        timeline, reason = timed_goals(meta, state_map)
        meta_counts['timed_goals_available'] += timeline is not None
        meta_counts['timed_goal_events'] += len(timeline) if timeline is not None else 0
        meta_counts[f'goal_status:{reason}'] += 1
        has_header = any(isinstance(p.get('stats'), dict) and 'Goals' in p['stats']
                         for key in ('team_zero', 'team_one') for p in (meta.get(key) or []) if isinstance(p, dict))
        meta_counts['header_player_goal_totals_available'] += has_header
        # Team 0/1 are color slots. The real schema does not establish organization IDs.
        teams = meta.get('teams')
        if isinstance(teams, list) and len(teams) == 2 and all(isinstance(t, dict) and t.get('id') for t in teams):
            meta_counts['explicit_team_ids_available'] += 1
    selected = ok.copy()
    if max_replays is not None:
        from .extract import select_replays
        selected = select_replays(index, max_replays, seed, manifest, raw_paths)
    ranges, state_counts, state_evidence = {}, Counter(), defaultdict(Counter)
    state_transitions, goal_checks, goal_sources = Counter(), Counter(), Counter()
    for key in ('replays_scanned', 'frame_timelines_available', 'frame_goal_events', 'ambiguous_goal_events',
                'replays_with_ambiguous_goals', 'timed_goals_available', 'frame_timelines_checked',
                'header_totals_available', 'goal_agreement_comparable_replays', 'goal_agreement_replays',
                'goal_disagreement_replays'):
        goal_checks[key] = 0
    goal_examples = []
    replay_metadata = {str(row['replay_id']): parsed_json(row.get('replay_meta'), {})
                       for row in selected.to_dict('records')}
    frame_checks, absent_shards = Counter(), []
    numeric = ['frame', 'current time', 'frame time', 'seconds remaining', 'game state', 'ball has been hit'] + BALL_COLUMNS
    numeric += [f'p{i} - {field}' for i in range(6) for field in ('boost level (raw replay units)', 'player demolished by')]
    seen = Counter()
    for number, (path, rows) in enumerate(selected.groupby('_frame_path', sort=True)):
        if not Path(path).exists():
            absent_shards.append(path)
            continue
        available = set(pq.ParquetFile(path).schema_arrow.names)
        essential = {'replay_id', 'frame', 'current time', 'frame time', 'seconds remaining', 'game state', 'ball has been hit'}
        if not essential <= available:
            raise ValueError(f'{path}: missing clock/state columns {sorted(essential - available)}')
        columns = ['replay_id'] + [x for x in numeric if x in available]
        for rid, frames in iter_frame_replays(Path(path), set(rows['replay_id']), columns=columns):
            seen[rid] += 1
            frame_checks['replays_scanned'] += 1
            frame_checks['frames_scanned'] += len(frames)
            for name in columns[1:]:
                _range_update(ranges, name, frames[name].to_numpy())
            t = frames['current time'].to_numpy(float)
            f = frames['frame'].to_numpy(float)
            rem = frames['seconds remaining'].to_numpy(float)
            state = frames['game state'].to_numpy(float)
            hit = frames['ball has been hit'].to_numpy(float)
            dt, df = np.diff(t), np.diff(f)
            frame_checks['nonincreasing_frame_steps'] += int(np.count_nonzero(df <= 0))
            frame_checks['nonincreasing_time_steps'] += int(np.count_nonzero(dt <= 0))
            frame_checks['time_gaps_over_0_1s'] += int(np.count_nonzero(dt > .1))
            frame_checks['negative_remaining_frames'] += int(np.count_nonzero(rem < 0))
            frame_checks['zero_remaining_frames'] += int(np.count_nonzero(rem == 0))
            frame_checks['remaining_over_300_frames'] += int(np.count_nonzero(rem > 300))
            frame_checks['noninteger_game_states'] += int(np.count_nonzero(np.isfinite(state) & (state != np.floor(state))))
            frame_checks['hit_rising_edges'] += int(np.count_nonzero((hit[1:] > 0) & (hit[:-1] <= 0)))
            frame_checks['hit_falling_edges'] += int(np.count_nonzero((hit[1:] <= 0) & (hit[:-1] > 0)))
            frame_checks['hit_positive_frames'] += int(np.count_nonzero(hit > 0))
            _range_update(ranges, 'delta_current_time', dt)
            _range_update(ranges, 'delta_frame', df)
            _range_update(ranges, 'delta_seconds_remaining', np.diff(rem))
            drem = np.diff(rem, prepend=np.nan)
            for value in np.unique(state[np.isfinite(state)]):
                mask = state == value
                name = str(int(value)) if value == int(value) else str(value)
                state_counts[name] += int(mask.sum())
                state_evidence[name]['frames'] += int(mask.sum())
                state_evidence[name]['hit_positive'] += int(np.count_nonzero(mask & (hit > 0)))
                state_evidence[name]['clock_decreases'] += int(np.count_nonzero(mask & (drem < 0)))
                state_evidence[name]['clock_increases'] += int(np.count_nonzero(mask & (drem > 0)))
                state_evidence[name]['clock_zero'] += int(np.count_nonzero(mask & (rem == 0)))
            ordered = frames.sort_values('frame', kind='stable')
            ordered_state = ordered['game state'].to_numpy(float)
            changed = (np.isfinite(ordered_state[:-1]) & np.isfinite(ordered_state[1:])
                       & (ordered_state[:-1] != ordered_state[1:]))
            for before, after in zip(ordered_state[:-1][changed], ordered_state[1:][changed]):
                state_transitions[f'{before:g}->{after:g}'] += 1
            # Coverage and agreement count replay IDs once, even when the storage
            # contract is violated by duplicate row groups (reported below).
            if seen[rid] == 1:
                meta = replay_metadata.get(rid)
                meta = meta if isinstance(meta, dict) else {}
                frame_timeline, evidence = frame_goals(ordered, state_map)
                meta_timeline, meta_reason = timed_goals(meta, state_map)
                goal_checks['replays_scanned'] += 1
                frame_complete = frame_timeline is not None and not evidence['ambiguous_goals']
                goal_checks['frame_timelines_available'] += frame_complete
                goal_checks['frame_goal_events'] += evidence['goal_events']
                goal_checks['ambiguous_goal_events'] += evidence['ambiguous_goals']
                goal_checks['replays_with_ambiguous_goals'] += bool(evidence['ambiguous_goals'])
                if meta_timeline is not None:
                    goal_checks['timed_goals_available'] += 1
                    goal_sources[meta_reason] += 1
                elif frame_complete:
                    goal_checks['timed_goals_available'] += 1
                    goal_sources['frame_state_transitions'] += 1
                else:
                    goal_sources['ambiguous_frame_goal_team' if frame_timeline is not None else meta_reason] += 1
                agreement = goal_agreement(frame_timeline, meta)
                if frame_timeline is not None:
                    goal_checks['frame_timelines_checked'] += 1
                    goal_checks['header_totals_available'] += goal_totals(meta) is not None
                if agreement is not None:
                    goal_checks['goal_agreement_comparable_replays'] += 1
                    goal_checks['goal_agreement_replays'] += agreement
                    goal_checks['goal_disagreement_replays'] += not agreement
                if (agreement is False or evidence['ambiguous_goals']) and len(goal_examples) < 20:
                    goal_examples.append(dict(replay_id=rid, frame_team_counts=evidence['team_counts'],
                                              header_team_counts=goal_totals(meta),
                                              ambiguous_goals=evidence['ambiguous_goals'], agreement=agreement))
        if run:
            run.metric(shards_scanned=number + 1, replays_scanned=frame_checks['replays_scanned'],
                       frames_scanned=frame_checks['frames_scanned'])
    missing_frames = set(selected['replay_id']) - set(seen)
    details = dict(
        counts_per_season_status_n_players=counts,
        observed=dict(index_rows=len(index), unique_replay_ids=index['replay_id'].nunique(), ok_games=len(ok),
                      failed_games=int((index['status'] == 'failed').sum()), modes=modes,
                      mode_total=mode_total, odd_player_games=odd, other_unclassified_ok_games=len(ok) - mode_total - odd,
                      gap=len(ok) - mode_total),
        supplied_reconciliation=dict(season_total=49259, mode_total=49165, odd_player_games=94,
            equation='49,259 - (1,586 + 786 + 46,793) = 94 odd-player-count parsed games.',
            note='134 parse failures and 26 deleted downloads are separate; never subtract them again from parsed games.'),
        metadata=dict(meta_counts), goal_field_shapes=dict(goal_fields), replay_meta_root_keys=dict(root_keys),
        identity_notes=['remote_id platform + value is used; names alone are not stable IDs.',
                        'Color team 0/1 is available but is not an organization ID.',
                        'Header player Goals totals cannot reconstruct goal times or pre-frame scores.'],
        player_ids_with_multiple_names=sum(len(v) > 1 for v in stable_ids.values()),
        metadata_decode_errors=metadata_errors[:20], series_coverage=dict(grouping),
        series_coverage_per_season={k: dict(v) for k, v in per_season.items()},
        missing_series_examples=unavailable_examples, manifest_entries=len(manifest),
        manifest_conflicts=conflicts, duplicate_index_replay_ids=duplicate_ids,
        frames=dict(frame_checks), frame_ranges=ranges, game_state_counts=dict(state_counts),
        game_state_transitions=dict(state_transitions),
        game_state_evidence={k: dict(v) for k, v in state_evidence.items()},
        state_map=state_map,
        goals=dict(goal_checks, timeline_sources=dict(goal_sources), disagreement_examples=goal_examples,
                   coverage_scope='unique_scanned_replays',
                   agreement_scope='scanned frame timelines with complete per-team header Goals totals',
                   ambiguity_policy='Unverified goal teams make frame timelines incomplete and cannot agree with header totals.'),
        missing_frame_shards=absent_shards, selected_replays_missing_frames=len(missing_frames),
        duplicate_frame_row_groups={k: v for k, v in seen.items() if v > 1},
        frame_scan_max_replays_per_season=max_replays,
        frame_scan_scope='eligible_3v3_complete_known_series_sample' if max_replays is not None else 'all_ok_replays',
        semantics={'game_state_codes': 'explicit_state_map' if state_map.get('live_states') is not None else 'unverified',
                   'ball_has_been_hit': 'candidate kickoff latch; edges and prevalence reported, not per-touch pulses',
                   'boost_units': 'raw replay units; range is evidence, no assumed 0..100 scale',
                   'demolished_by': 'actor/event/state/sentinel semantics unverified',
                   'overtime': state_map.get('overtime_detection', 'explicit overtime_states if configured; otherwise unknown'),
                   'coordinates': 'blue/team 0 attacks +y per supplied kickoff validation; units require audit'},
    )
    metrics = dict(index_games=len(index), ok_games=len(ok), failed_games=int((index['status'] == 'failed').sum()),
                   odd_player_games=odd, scanned_frames=frame_checks['frames_scanned'],
                   series_coverage=(len(index) - grouping.get('missing', 0) - grouping.get('manifest_conflict', 0)) / max(len(index), 1),
                   timed_goal_coverage=goal_checks['timed_goals_available'] / max(goal_checks['replays_scanned'], 1),
                   metadata_timed_goal_coverage=meta_counts['timed_goals_available'] / max(len(index), 1),
                   frame_derived_timed_goal_coverage=goal_checks['frame_timelines_available'] / max(goal_checks['replays_scanned'], 1),
                   goal_agreement_rate=(goal_checks['goal_agreement_replays'] / goal_checks['goal_agreement_comparable_replays']
                                        if goal_checks['goal_agreement_comparable_replays'] else None),
                   stable_player_id_coverage=meta_counts['stable_player_ids'] / max(meta_counts['players_total'], 1))
    return metrics, details


def markdown(metrics, details):
    lines = ['# P3 data audit', '', 'Counts below were computed from the supplied data path; source totals are listed separately.', '',
             '| Season | Status | Players | Games |', '|---|---|---:|---:|']
    for row in details['counts_per_season_status_n_players']:
        lines.append(f"| {row['season']} | {row['status']} | {row['n_players']} | {row['games']} |")
    lines += ['', '## The 94-game reconciliation', '', details['supplied_reconciliation']['equation'],
              details['supplied_reconciliation']['note'], '',
              f"Observed parsed-game gap: {details['observed']['gap']}; odd-player games: {details['observed']['odd_player_games']}.",
              '', '## Coverage and semantics', '',
              f"Series coverage: {metrics['series_coverage']:.1%}; timed-goal coverage among scanned replays: {metrics['timed_goal_coverage']:.1%}; stable player-ID coverage: {metrics['stable_player_id_coverage']:.1%}.",
              f"Metadata-only timed-goal coverage across index rows: {metrics['metadata_timed_goal_coverage']:.1%}; complete frame-derived timelines among scanned replays: {metrics['frame_derived_timed_goal_coverage']:.1%}.",
              f"Frame scan: {metrics['scanned_frames']:,} frames; {details['selected_replays_missing_frames']} selected replays missing locally.",
              '', 'Header goal totals cross-check frame-derived events; they do not establish event times.',
              'The default state_map_rlcs.json supplies the empirically decoded RLCS states; --state-map overrides it.',
              'Goals use live-to-goal-state transitions and the preceding ball y coordinate, with ambiguous scoring teams reported.',
              'With the default map, a live-to-kickoff transition at zero seconds starts overtime; its live state code is unchanged.',
              'The explicit exploratory clock/hit heuristic does not validate these semantics.',
              'Raw demolition and boost ranges are reported without assuming a unit or duration convention.',
              '', '## Goal agreement', '']
    goals = details['goals']
    agreement = metrics['goal_agreement_rate']
    rate = f'{agreement:.1%}' if agreement is not None else 'unavailable (no comparable header totals)'
    lines += [f"Per-replay agreement of both frame-derived team counts with summed player Goals: {rate} "
              f"({goals['goal_agreement_replays']}/{goals['goal_agreement_comparable_replays']} comparable replays).",
              f"Detected goal events: {goals['frame_goal_events']}; ambiguous scoring teams: {goals['ambiguous_goal_events']}; "
              f"disagreeing replays: {goals['goal_disagreement_replays']}.",
              '', '## Game-state codes and transitions', '', '| Code | Frames |', '|---|---:|']
    for code, count in sorted(details['game_state_counts'].items(), key=lambda pair: float(pair[0])):
        lines.append(f'| {code} | {count} |')
    lines += ['', 'Transitions count adjacent changed finite codes within a replay, ordered by parser frame.',
              '', '| Transition | Count |', '|---|---:|']
    for transition, count in sorted(details['game_state_transitions'].items()):
        lines.append(f'| {transition} | {count} |')
    lines += ['', '## Clock and state ranges', '', '| Field | Min | Max | Missing |', '|---|---:|---:|---:|']
    for name in ('frame', 'current time', 'frame time', 'seconds remaining', 'game state', 'ball has been hit'):
        item = details['frame_ranges'].get(name, {})
        lines.append(f"| {name} | {item.get('min')} | {item.get('max')} | {item.get('missing')} |")
    lines += ['', 'Detailed state evidence, metadata fields, grouping sources and anomaly counts are in audit.json.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--max-replays', type=int, help='Optional frame scan cap per season; all indexes/metadata still audited')
    parser.add_argument('--state-map', type=Path, help='Explicit decoder configuration (default: state_map_rlcs.json)')
    args = parser.parse_args(argv)
    with Run(args, 'audit', method='Native-schema audit') as run:
        run.idea('p3-data-audit', 'Data and parser semantics audit', 'running', motivation='Check source eligibility, identity and clock semantics')
        config = load_state_map(args.state_map)
        metrics, details = audit(args.data_root, run, args.max_replays, args.seed, config)
        run.result('audit', metrics, notes='Source reference counts are not treated as measured fixture/cluster counts.', details=details)
        (args.output / 'results' / 'audit.md').write_text(markdown(metrics, details), encoding='utf-8')
        bad = bool(details['manifest_conflicts'] or details['duplicate_index_replay_ids'])
        run.idea('p3-data-audit', 'Data and parser semantics audit', 'pruned' if bad else 'promising',
                 prune_reason='Conflicting replay/series membership requires resolution' if bad else '')


if __name__ == '__main__':
    main()
