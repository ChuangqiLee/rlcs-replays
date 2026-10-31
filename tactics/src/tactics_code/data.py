"""Real-schema readers and the compact, pickle-free shard contract."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

DEFAULT_DATA_ROOT = (Path.home() / "workspace/rlcs-replays/data")
DEFAULT_STATE_MAP = Path('state_map_rlcs.json')
AXES = ('x', 'y', 'z')
BALL_COLUMNS = [f'Ball - {kind} {a}' for kind in ('position', 'linear velocity') for a in AXES]
PLAYER_COLUMNS = [[f'p{i} - {kind} {a}' for kind in ('position', 'linear velocity') for a in AXES]
                  + [f'p{i} - boost level (raw replay units)', f'p{i} - player demolished by']
                  for i in range(6)]
FLAG_COLUMNS = [[f'p{i} - {f}' for f in ('dodge active', 'jump active', 'double jump active', 'any_jump_active')]
                for i in range(6)]
FRAME_COLUMNS = ['replay_id', 'frame', 'current time', 'frame time', 'seconds remaining', 'game state',
                 'ball has been hit'] + BALL_COLUMNS + sum(PLAYER_COLUMNS, []) + sum(FLAG_COLUMNS, [])


def parsed_json(value, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def stable_player_id(player: dict) -> str | None:
    remote = player.get('remote_id')
    if isinstance(remote, dict) and remote:
        parts = [(str(k), str(v)) for k, v in remote.items() if v is not None and str(v) not in ('', '0', 'None')]
        return '|'.join(f'{k}:{v}' for k, v in sorted(parts)) or None
    return None  # Names and slot numbers are deliberately not identity keys.


def roster_key(ids) -> str | None:
    if len(ids) != 3 or any(x is None for x in ids) or len(set(ids)) != 3:
        return None
    return 'roster:' + hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest()[:20]


def frame_root(root: Path) -> Path:
    root = Path(root)
    candidate = root / 'frames' / 'fps30'
    return candidate if candidate.exists() else root


def index_paths(root: Path) -> list[Path]:
    return sorted(frame_root(root).rglob('*.index.parquet'))


def read_index(root: Path) -> pd.DataFrame:
    pieces = []
    for path in index_paths(root):
        df = pd.read_parquet(path)
        for column in ('replay_id', 'season', 'status', 'n_players', 'players', 'replay_meta'):
            if column not in df:
                raise ValueError(f'{path}: required index column {column!r} missing')
        df['_index_path'] = str(path)
        df['_frame_path'] = str(path.with_name(path.name.replace('.index.parquet', '.parquet')))
        pieces.append(df)
    if not pieces:
        raise FileNotFoundError(f'No *.index.parquet beneath {frame_root(root)}')
    result = pd.concat(pieces, ignore_index=True)
    result['replay_id'] = result['replay_id'].astype(str)
    result['season'] = result['season'].astype(str)
    return result


def load_manifest(root: Path) -> tuple[dict, list]:
    rows, conflicts = {}, []
    path = Path(root) / 'manifest' / 'replays.jsonl'
    if not path.exists():
        return rows, conflicts
    with path.open(encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                rid = str(item['id'])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f'{path}:{line_no}: invalid replay manifest') from exc
            if rid in rows and (rows[rid].get('group'), rows[rid].get('group_path'), rows[rid].get('season')) != (
                    item.get('group'), item.get('group_path'), item.get('season')):
                conflicts.append(rid)
                rows[rid]['_conflict'] = True
            else:
                rows[rid] = item
    for rid in conflicts:
        rows[rid]['_conflict'] = True
    return rows, sorted(set(conflicts))


def raw_path_lookup(root: Path) -> dict[str, str]:
    """Directory names only: no raw replay decoding or network access."""
    root = Path(root) / 'raw' / 'kaggle'
    lookup = {}
    if root.exists():
        for path in root.rglob('*.replay'):
            rid = path.stem
            value = str(path)
            if rid in lookup and lookup[rid] != value:
                lookup[rid] = ''  # Ambiguous paths cannot define a grouping.
            else:
                lookup[rid] = value
    # A scratch staging helper may supply paths without copying 56 GB of raw files.
    saved = root.parent.parent / 'manifest' / 'kaggle_paths.json'
    if saved.exists():
        for key, value in json.loads(saved.read_text()).items():
            lookup.setdefault(key, value)
    return lookup


def group_metadata(row: dict, manifest: dict, raw_paths: dict) -> dict:
    rid, season = str(row['replay_id']), str(row['season'])
    item = manifest.get(rid, {})
    path = item.get('group_path') or []
    if isinstance(path, str):
        path = [x for x in path.split('/') if x]
    source, sid = None, None
    if item.get('_conflict') or (item.get('season') and item['season'] != season):
        path = []
        source = 'manifest_conflict'
    elif len(path) >= 3:
        sid = season + ':' + str(item.get('group') or '/'.join(path))
        source = 'manifest_group_path'
    if sid is None and source != 'manifest_conflict':
        filename = raw_paths.get(rid) or row.get('source_file')
        if isinstance(filename, str) and ('kaggle' in filename.lower()):
            parts = Path(filename).parts
            markers = [i for i, p in enumerate(parts) if p.lower() == 'kaggle']
            if markers and filename.endswith('.replay'):
                path = list(parts[markers[-1] + 1:-1])
                if len(path) >= 3:
                    sid = season + ':kaggle:' + '/'.join(path)
                    source = 'kaggle_folder_path'
    region_names = {'Europe', 'North America', 'South America', 'Oceania', 'Middle East & North Africa',
                    'Middle East and North Africa', 'Asia-Pacific', 'Asia Pacific', 'Sub-Saharan Africa',
                    'MENA', 'APAC', 'SSA', 'EU', 'NA', 'SAM', 'OCE'}
    region = next((x for x in path if x in region_names), None)
    return dict(series_id=sid, series_source=source, event='/'.join(path[:2]) if len(path) >= 2 else None,
                region=region, stage=path[-2] if len(path) >= 3 else None,
                group_path=json.dumps(path), date=item.get('date'))


def load_state_map(path: Path | str | None = None) -> dict:
    """Load the reviewed RLCS map by default, with explicit maps replacing it."""
    target = Path(path) if path is not None else DEFAULT_STATE_MAP
    if path is None and not target.exists():
        target = Path(__file__).resolve().parent.parent / DEFAULT_STATE_MAP
    config = json.loads(target.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError(f'{target}: state map must be a JSON object')
    return config


def goal_totals(meta: dict) -> list[int] | None:
    """Complete per-team player Goals totals, used only as a cross-check."""
    totals = []
    for key in ('team_zero', 'team_one'):
        players = meta.get(key)
        if not isinstance(players, list) or not players:
            return None
        total = 0
        for player in players:
            stats = player.get('stats') if isinstance(player, dict) else None
            value = stats.get('Goals') if isinstance(stats, dict) else None
            if value is None or isinstance(value, bool):
                return None
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
            if not np.isfinite(value) or value < 0 or not value.is_integer():
                return None
            total += int(value)
        totals.append(total)
    return totals


def goal_agreement(events, meta: dict) -> bool | None:
    totals = goal_totals(meta)
    if events is None or totals is None:
        return None
    return (all(team in (0, 1) for _, team, _ in events)
            and totals == [sum(team == i for _, team, _ in events) for i in (0, 1)])


def frame_goals(df: pd.DataFrame, config: dict) -> tuple[list | None, dict]:
    """Native-frame live -> post-goal events, before subsampling or rotation.

    The event is the first post-goal frame. Its team uses only the preceding
    ball position: blue attacks +y, orange -y. None marks an ambiguous scorer;
    header totals never fill in missing goal teams or times.
    """
    diagnostics = dict(enabled=config.get('goal_detection') == 'frame_state_transitions',
                       goal_events=0, ambiguous_goals=0, team_counts=[0, 0])
    if not diagnostics['enabled']:
        return None, diagnostics
    state = df['game state'].to_numpy(dtype=float)
    live = np.isin(state, config.get('live_states', []))
    post_goal = np.isin(state, config.get('goal_replay_states', []))
    if not live.any():
        return None, diagnostics
    frame = df['frame'].to_numpy(dtype=float)
    ball_y = (df['Ball - position y'].to_numpy(dtype=float) if 'Ball - position y' in df
              else np.full(len(df), np.nan))
    indices = np.flatnonzero(live[:-1] & post_goal[1:]) + 1
    events = []
    for i in indices:
        y = ball_y[i - 1]
        team = int(y < 0) if np.isfinite(y) and abs(y) > 5000 else None
        events.append((float(frame[i]), team, 'frame'))
        if team is None:
            diagnostics['ambiguous_goals'] += 1
        else:
            diagnostics['team_counts'][team] += 1
    diagnostics['goal_events'] = len(events)
    return events, diagnostics


def frame_overtime(df: pd.DataFrame, config: dict) -> np.ndarray:
    """Track overtime across reused state codes using the regulation-end reset."""
    state = df['game state'].to_numpy(dtype=float)
    remaining = df['seconds remaining'].to_numpy(dtype=float)
    live = np.isin(state, config.get('live_states', []))
    kickoff = np.isin(state, config.get('kickoff_states', []))
    post_goal = np.isin(state, config.get('goal_replay_states', []))
    overtime = np.full(len(df), np.nan, np.float32)
    overtime[live | kickoff | post_goal] = 0
    pending, active = False, False
    for i in range(1, len(df)):
        if live[i - 1] and post_goal[i]:
            # A goal at zero seconds is still a goal, not the OT-start reset.
            pending, active = False, False
        elif live[i - 1] and kickoff[i] and remaining[i] == 0:
            pending = True
        if pending and live[i]:
            pending, active = False, True
        if active and live[i]:
            overtime[i] = 1
    return overtime


def timed_goals(meta: dict, config: dict | None = None) -> tuple[list[tuple[float, int, str]] | None, str]:
    """Return a complete explicitly present timeline, or unknown (never infer from totals).

    Native forms accepted: goals:[{frame,team}] or goals:[{time,team}].
    Nonstandard metadata requires goals_key/goal_time_key/goal_time_unit/goal_team_key.
    Frames are parser frame numbers; 'time' must be in the current-time clock domain.
    """
    config = config or {}
    key = config.get('goals_key', 'goals')
    events = meta.get(key)
    if not isinstance(events, list):
        return None, 'missing_timed_goal_list'
    out = []
    for event in events:
        if not isinstance(event, dict):
            return None, 'unrecognized_goal_event'
        team = event.get(config.get('goal_team_key', 'team'))
        if isinstance(team, bool) or team not in (0, 1):
            return None, 'unrecognized_goal_team'
        if config.get('goal_time_key'):
            value = event.get(config['goal_time_key'])
            unit = config.get('goal_time_unit', 'time')
        elif 'frame' in event:
            value, unit = event['frame'], 'frame'
        else:
            value, unit = event.get('time'), 'time'
        if unit not in ('time', 'frame') or not isinstance(value, (int, float)) or not np.isfinite(value):
            return None, 'unrecognized_goal_clock'
        out.append((float(value), int(team), unit))
    if goal_agreement(out, meta) is False:
        return None, 'goal_list_disagrees_with_header_totals'
    return out, 'explicit_complete_goal_list'


def iter_frame_replays(path: Path, selected: set[str] | None = None, columns=None) -> Iterator[tuple[str, pd.DataFrame]]:
    """One row group per replay is the documented storage contract; validate it."""
    import pyarrow.parquet as pq
    file = pq.ParquetFile(path)
    actual = set(file.schema_arrow.names)
    columns = FRAME_COLUMNS if columns is None else columns
    missing = set(columns) - actual
    if missing:
        raise ValueError(f'{path}: missing real-schema columns {sorted(missing)}')
    replay_col = file.schema_arrow.names.index('replay_id')
    for group in range(file.num_row_groups):
        stats = file.metadata.row_group(group).column(replay_col).statistics
        if selected is not None and stats is not None and stats.has_min_max and stats.min == stats.max:
            rid = str(stats.min)
            if rid not in selected:
                continue
        table = file.read_row_group(group, columns=columns)
        frame = table.to_pandas()
        if frame.empty:
            continue
        ids = frame['replay_id'].astype(str).unique()
        if len(ids) != 1:
            raise ValueError(f'{path} row group {group}: expected one replay, got {len(ids)}')
        rid = ids[0]
        if selected is None or rid in selected:
            yield rid, frame


def iter_compact(path: Path | str, splits: set[str] | None = None) -> Iterator[tuple[dict, dict[str, np.ndarray]]]:
    """Yield (metadata, frame arrays); only one compressed shard is resident at once."""
    path = Path(path)
    files = [path] if path.suffix == '.npz' else sorted(path.rglob('*.npz'))
    for file in files:
        metadata = file.with_suffix('.parquet')
        if not metadata.exists():
            continue
        records = pd.read_parquet(metadata).to_dict('records')
        if splits is not None:
            records = [r for r in records if r.get('split') in splits]
        if not records:
            continue
        with np.load(file, allow_pickle=False) as loaded:
            arrays = {key: loaded[key] for key in loaded.files}
        for record in records:
            start, stop = int(record['start']), int(record['stop'])
            yield record, {key: value[start:stop] for key, value in arrays.items()}
