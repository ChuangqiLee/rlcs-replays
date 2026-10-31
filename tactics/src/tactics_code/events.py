"""Native goal events and conservative terminal certification for P4 development.

Goal detection is deliberately the SAME replay-local decoder as audit.py. Header
player Goals validate the resulting timeline; they never supply a goal label or
its timestamp. A count match does not establish sub-frame timing accuracy.
Only explicitly allowlisted 2021--2025 paths are opened, including native indexes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .data import (DEFAULT_DATA_ROOT, decode_replay_states, frame_goals,
                   goal_agreement, goal_totals, load_state_map, parsed_json)

ALLOWED_SEASONS = ("rlcs-21-22", "rlcs-22-23", "rlcs-2024", "rlcs-2025")
NATIVE_COLUMNS = ["replay_id", "frame", "current time", "seconds remaining",
                  "game state", "ball has been hit", "Ball - position y"]
GOAL_COLUMNS = ["replay_id", "season", "series_id", "goal_number", "frame", "time",
                "scoring_team", "seconds_remaining", "regulation", "overtime",
                "last_live_frame", "last_live_time", "timing_bracket_seconds",
                "validated", "source"]
REPLAY_COLUMNS = ["replay_id", "season", "series_id", "validated", "goal_agreement",
                  "header_goals_0", "header_goals_1", "detected_goals_0",
                  "detected_goals_1", "n_goals", "n_native_frames", "native_path",
                  "observed_start_time", "observed_end_time", "regulation_end_time",
                  "regulation_end_frame", "regulation_end_source", "has_overtime",
                  "overtime_start_time", "overtime_start_frame", "terminal_time",
                  "terminal_frame", "terminal_verified", "terminal_reason",
                  "clock_zero_first_time", "max_time_gap_seconds", "gap_start_times",
                  "gap_end_times", "failure_reason", "decoding_diagnostics",
                  "state_map_sha256"]


def guard_path(path):
    """Reject test season paths/symlinks, allowing native extraction timestamps.

    Native filenames contain 20261030: that is an extraction date, not a season.
    Season components and standalone 2026 markers are still rejected.
    """
    path = Path(path)
    if any(re.search(r"(?<![0-9])2026(?![0-9])", str(p)) for p in (path, path.resolve())):
        raise ValueError("NEVER read 2026 (test)")
    if "test" in path.resolve().parts:
        raise ValueError("Test-split path forbidden")
    return path


def _check_record(row):
    if str(row.get("season")) not in ALLOWED_SEASONS:
        raise ValueError(f"Forbidden or unknown event season: {row.get('season')!r}")
    if row.get("split") not in (None, "train", "val"):
        raise ValueError("NEVER read test rows")
    expected = "val" if row["season"] == "rlcs-2025" else "train"
    if row.get("split") is not None and row["split"] != expected:
        raise ValueError("Season/split mismatch")


def native_index_for(selected_records, data_root=DEFAULT_DATA_ROOT):
    """Resolve selected IDs from allowed-season indexes, never global read_index.

    All selected replay IDs must exist exactly once. Metadata scans may inspect
    allowed-season index rows, but native frame row groups are selected by ID.
    """
    records = (selected_records.to_dict("records") if isinstance(selected_records, pd.DataFrame)
               else list(selected_records))
    requested = {}
    for row in records:
        _check_record(row)
        rid = str(row["replay_id"])
        if rid in requested and requested[rid]["season"] != row["season"]:
            raise ValueError(f"Conflicting season for {rid}")
        requested[rid] = row
    root = guard_path(data_root)
    native = root / "frames" / "fps30"
    if native.exists():
        root = native
    resolved = {}
    for season in sorted({row["season"] for row in requested.values()}):
        directory = guard_path(root / season)
        wanted = {rid for rid, row in requested.items() if row["season"] == season}
        for index_path in sorted(directory.glob("*.index.parquet")):
            index_path = guard_path(index_path)
            index = pd.read_parquet(index_path)
            if "season" not in index or not index["season"].astype(str).eq(season).all():
                raise ValueError(f"Unexpected native index season: {index_path}")
            for row in index[index["replay_id"].astype(str).isin(wanted)].to_dict("records"):
                rid = str(row["replay_id"])
                if rid in resolved:
                    raise ValueError(f"Duplicate native index replay: {rid}")
                source = guard_path(index_path.with_name(index_path.name.replace(".index.parquet", ".parquet")))
                resolved[rid] = dict(requested[rid], **{k: v for k, v in row.items()
                                                       if k not in ("series_id", "split")})
                resolved[rid]["_frame_path"] = str(source)
    missing = sorted(set(requested) - set(resolved))
    if missing:
        raise ValueError(f"Native indexes missing {len(missing)} selected replays: {missing[:5]}")
    return [resolved[rid] for rid in sorted(resolved)]


def _native_replays(path, selected):
    """Read only selected native row groups; fail closed without ID statistics.

    Unlike a read-all-then-filter fallback, this enforces the smoke replay cap.
    """
    import pyarrow.parquet as pq
    file = pq.ParquetFile(guard_path(path))
    missing = set(NATIVE_COLUMNS) - set(file.schema_arrow.names)
    if missing:
        raise ValueError(f"Missing native event columns: {sorted(missing)}")
    replay_col = file.schema_arrow.names.index("replay_id")
    seen = set()
    for number in range(file.num_row_groups):
        stats = file.metadata.row_group(number).column(replay_col).statistics
        if stats is None or not stats.has_min_max or stats.min != stats.max:
            raise ValueError(f"Cannot enforce selected-only native reads: {path} group {number}")
        rid = str(stats.min)
        if rid not in selected:
            continue
        if rid in seen:
            raise ValueError(f"Duplicate native row group: {rid}")
        frame = file.read_row_group(number, columns=NATIVE_COLUMNS).to_pandas()
        if not frame["replay_id"].astype(str).eq(rid).all():
            raise ValueError(f"Native row-group replay IDs disagree with statistics: {rid}")
        seen.add(rid)
        yield rid, frame
    if seen != set(selected):
        raise ValueError(f"Selected native frames missing: {sorted(set(selected) - seen)}")


def build_replay_events(frames, row, state_map):
    """Return (goal records, replay certification) from one native replay.

    A terminal is certified only by a zero-clock non-goal live exit with no later
    live frame, or a final zero-clock/OT goal with no later live frame. A plain
    end-of-file is censoring, even if all goals agree with the header. Events are
    stamped at the first post-goal frame, retaining the last-live timing bracket.
    """
    _check_record(row)
    if state_map.get("state_decoding") != "per_replay_decoded" or state_map.get("goal_detection") != "frame_state_transitions":
        raise ValueError("P4 events require audit.py's per-replay state decoding and frame goals")
    ordered = frames.sort_values("frame", kind="stable").reset_index(drop=True)
    rid = str(row["replay_id"])
    summary = dict.fromkeys(REPLAY_COLUMNS)
    summary.update(replay_id=rid, season=str(row["season"]), series_id=row.get("series_id"),
                   n_native_frames=len(ordered), native_path=str(row.get("_frame_path", "")),
                   state_map_sha256=hashlib.sha256(json.dumps(state_map, sort_keys=True).encode()).hexdigest())
    if ordered.empty:
        summary.update(validated=False, terminal_verified=False, failure_reason="empty_native_replay")
        return [], summary
    frame = ordered["frame"].to_numpy(float)
    time = ordered["current time"].to_numpy(float)
    rem = ordered["seconds remaining"].to_numpy(float)
    failures = []
    if not np.isfinite(frame).all() or np.any(np.diff(frame) <= 0):
        failures.append("nonincreasing_or_invalid_frame")
    if not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        failures.append("nonincreasing_or_invalid_time")
    decoded = decode_replay_states(ordered)
    failures.extend(decoded["diagnostics"]["failures"])
    timeline, evidence = frame_goals(ordered, state_map, decoded)
    meta = parsed_json(row.get("replay_meta"), {})
    totals = goal_totals(meta)
    agreement = goal_agreement(timeline, meta)
    if agreement is not True:
        failures.append("header_goal_totals_missing" if totals is None else "goal_count_disagreement")
    if timeline is None or evidence["ambiguous_goals"]:
        failures.append("incomplete_goal_timeline")
    gaps = np.flatnonzero(np.diff(time) > .2)
    # Missing intervals are exposed to the outcome builder, not mislabeled as
    # no-goal follow-up. Goal count validation alone does not repair these gaps.
    summary.update(observed_start_time=float(time[0]), observed_end_time=float(time[-1]),
                   goal_agreement=agreement, header_goals_0=totals[0] if totals else None,
                   header_goals_1=totals[1] if totals else None,
                   detected_goals_0=evidence["team_counts"][0], detected_goals_1=evidence["team_counts"][1],
                   n_goals=len(timeline or []), max_time_gap_seconds=float(np.max(np.diff(time))) if len(time)>1 else None,
                   gap_start_times=json.dumps(time[gaps].tolist()), gap_end_times=json.dumps(time[gaps+1].tolist()),
                   decoding_diagnostics=json.dumps(decoded["diagnostics"], sort_keys=True))
    live, overtime = decoded["live"], decoded["overtime"]
    ot_indices = np.flatnonzero(live & (overtime == 1))
    zero_indices = np.flatnonzero(live & (rem == 0))
    summary.update(has_overtime=bool(len(ot_indices)),
                   overtime_start_time=float(time[ot_indices[0]]) if len(ot_indices) else None,
                   overtime_start_frame=int(frame[ot_indices[0]]) if len(ot_indices) else None,
                   clock_zero_first_time=float(time[zero_indices[0]]) if len(zero_indices) else None,
                   terminal_verified=False, terminal_reason="unverified_end_of_file")
    end_frames = decoded["diagnostics"].get("end_of_regulation_frames", [])
    end_indices = [int(np.searchsorted(frame, value)) for value in end_frames]
    # The decoder's end list can contain later zero-clock exits; the first is
    # the regulation boundary. Clock reaching zero by itself is NOT game end.
    if end_indices:
        j = end_indices[0]
        summary.update(regulation_end_time=float(time[j]), regulation_end_frame=int(frame[j]),
                       regulation_end_source="decoded_zero_clock_non_goal_exit")
    goals = []
    for number, (goal_frame, team, unit) in enumerate(timeline or [], 1):
        if unit != "frame":
            raise ValueError("Audited native goal clock must be frame")
        i = int(np.searchsorted(frame, goal_frame))
        if i <= 0 or i >= len(frame) or frame[i] != goal_frame:
            failures.append("goal_frame_not_found")
            continue
        is_ot = bool(overtime[i-1] == 1)
        goals.append(dict(replay_id=rid, season=str(row["season"]), series_id=row.get("series_id"),
                          goal_number=number, frame=int(goal_frame), time=float(time[i]), scoring_team=team,
                          seconds_remaining=float(rem[i-1]), regulation=not is_ot, overtime=is_ot,
                          last_live_frame=int(frame[i-1]), last_live_time=float(time[i-1]),
                          timing_bracket_seconds=float(time[i]-time[i-1]), validated=False,
                          source="audit_per_replay_live_exit_ball_y"))
        if not live[i:].any() and (is_ot or rem[i-1] == 0):
            # An equalizer at zero should lead to OT; absent OT is truncation.
            score_unequal = totals is not None and totals[0] != totals[1]
            if score_unequal:
                summary.update(terminal_time=float(time[i]), terminal_frame=int(frame[i]),
                               terminal_verified=True, terminal_reason="final_overtime_goal" if is_ot else "final_zero_clock_goal")
                if not is_ot and summary["regulation_end_time"] is None:
                    summary.update(regulation_end_time=float(time[i]), regulation_end_frame=int(frame[i]),
                                   regulation_end_source="final_zero_clock_goal")
    for i in end_indices:
        if not live[i:].any() and totals is not None and totals[0] != totals[1]:
            summary.update(terminal_time=float(time[i]), terminal_frame=int(frame[i]),
                           terminal_verified=True, terminal_reason="final_zero_clock_non_goal_exit")
    validated = not failures
    summary.update(validated=validated, failure_reason=";".join(sorted(set(failures))))
    if not validated:
        summary["terminal_verified"] = False
    for goal in goals:
        goal["validated"] = validated
    return goals, summary


def build_events(selected_records, artifacts_dir, data_root=DEFAULT_DATA_ROOT,
                 state_map_path=Path("state_map_rlcs.json")):
    """Build goals/replay tables for selected compact metadata; write two parquet files.

    Both focal-team views may be supplied. Neither 2026 data nor unrelated native
    replay frames are opened. Every selected replay gets an explicit audit row.
    """
    state_map = load_state_map(guard_path(state_map_path))
    rows = native_index_for(selected_records, data_root)
    lookup = {str(row["replay_id"]): row for row in rows}
    by_path = {}
    for rid, row in lookup.items():
        by_path.setdefault(row["_frame_path"], set()).add(rid)
    goals, summaries = [], []
    for path, ids in sorted(by_path.items()):
        for rid, frames in _native_replays(path, ids):
            events, summary = build_replay_events(frames, lookup[rid], state_map)
            goals.extend(events)
            summaries.append(summary)
    goal_table = pd.DataFrame(goals, columns=GOAL_COLUMNS)
    replay_table = pd.DataFrame(summaries, columns=REPLAY_COLUMNS)
    out = Path(artifacts_dir)
    out.mkdir(parents=True, exist_ok=True)
    goal_table.to_parquet(out / "goal_events.parquet", index=False)
    replay_table.to_parquet(out / "replay_events.parquet", index=False)
    return goal_table, replay_table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True, help="Selected compact metadata parquet; development rows only")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--state-map", type=Path, default=Path("state_map_rlcs.json"))
    args = parser.parse_args(argv)
    selected = pd.read_parquet(guard_path(args.selection))
    goals, replays = build_events(selected, args.artifacts, args.data_root, args.state_map)
    print(json.dumps(dict(replays=len(replays), goals=len(goals),
                          validated_replays=int(replays["validated"].sum()),
                          verified_terminals=int(replays["terminal_verified"].sum()))))


if __name__ == "__main__":
    main()
