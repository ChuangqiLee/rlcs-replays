"""Generate REAL-schema parquet row groups, indices and manifest for smoke tests.

The original fixture uses synthetic state codes; make_rlcs_replay uses the
empirically decoded RLCS 73/78/96 codes and an integer regulation/OT clock.
Run: python -m tests.synthetic --output tests/_synthetic/data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEASONS = ['rlcs-21-22', 'rlcs-22-23', 'rlcs-2024', 'rlcs-2025', 'rlcs-2026']
STATE_MAP = {'live_states': [1, 4], 'regulation_states': [0, 1, 3],
             'overtime_states': [4], 'kickoff_states': [0], 'goal_replay_states': [3],
             'demolition_sentinel': -1}


def make_replay(season='rlcs-2024', series=0, game=0, seconds=40, seed=42):
    rng = np.random.default_rng(seed + series * 100 + game)
    rid = f'{season}-series{series}-game{game}'
    n = int(seconds * 30)
    t = np.arange(n, dtype=np.float32) / 30
    data = {'replay_id': [rid] * n, 'frame': np.arange(n, dtype=np.int64)}
    phase = .6 * series + .2 * game
    ball = np.column_stack((1200 * np.sin(t / 3 + phase),
                            2300 * np.sin(t / 7 + phase), 180 + 70 * np.sin(t)))
    for subject in ['Ball'] + [f'p{i}' for i in range(6)]:
        if subject == 'Ball':
            pos = ball
        else:
            slot = int(subject[1:])
            sign = 1 if slot < 3 else -1
            role = slot % 3
            pos = np.column_stack((ball[:, 0] * .6 + 550 * np.cos(t / 4 + role * 2),
                                   ball[:, 1] * .4 - sign * (400 + 750 * role)
                                   + 450 * np.sin(t / 3 + role * 2 + phase),
                                   np.full(n, 17.)))
            pos += rng.normal(0, 2, pos.shape)
        vel = np.gradient(pos, 1 / 30, axis=0)
        for family, values in [('position', pos), ('linear velocity', vel),
                               ('rotation', np.zeros_like(pos)), ('angular velocity', np.zeros_like(pos))]:
            for j, axis in enumerate('xyz'):
                data[f'{subject} - {family} {axis}'] = values[:, j].astype(np.float32)
        if subject != 'Ball':
            data[f'{subject} - boost level (raw replay units)'] = np.full(n, 150., np.float32)
            for flag in ['dodge active', 'jump active', 'double jump active', 'any_jump_active']:
                data[f'{subject} - {flag}'] = np.zeros(n, np.float32)
            data[f'{subject} - player demolished by'] = np.full(n, -1., np.float32)
    state = np.ones(n, np.float32)
    state[:30] = 0
    middle = n // 2
    state[middle:middle + 30] = 3
    state[middle + 30:middle + 60] = 0
    # One series exercises explicitly mapped OT, including a count-up timer.
    if series % 4 == 3:
        state[-180:] = 4
    hit = (state != 0).astype(np.float32)
    remaining = 78. - t
    remaining[state == 4] = np.arange(np.count_nonzero(state == 4)) / 30
    data.update({'current time': t, 'frame time': np.full(n, 1 / 30, np.float32),
                 'seconds remaining': remaining.astype(np.float32), 'game state': state,
                 'ball has been hit': hit})
    # Include a missing car without changing six-player mode eligibility.
    data['p2 - position x'][45:48] = np.nan
    roster_a, roster_b = series % 2, 2 + series % 2
    players = [{'team': i // 3, 'name': f'Player-{r}-{i % 3}',
                'remote_id': {'Steam': f'{r:02d}{i % 3:015d}'}}
               for i, r in enumerate([roster_a] * 3 + [roster_b] * 3)]
    meta = {'goals': [{'frame': 0, 'team': game % 2}],
            'team_zero': [dict(p, stats={'Goals': int(i == 0 and game % 2 == 0), 'Team': 0}) for i, p in enumerate(players[:3])],
            'team_one': [dict(p, stats={'Goals': int(i == 0 and game % 2 == 1), 'Team': 1}) for i, p in enumerate(players[3:])],
            'game_type': {'playlist_id': 24}}
    path = f'raw/kaggle/{season}/Event-{series % 2}/Playoffs/Series-{series}/{rid}.replay'
    index = {'replay_id': rid, 'season': season, 'source_file': path, 'status': 'ok',
             'error': None, 'n_players': 6, 'n_frames': n, 'fps': 30,
             'players': json.dumps(players), 'replay_meta': json.dumps(meta)}
    manifest = {'id': rid, 'season': season, 'group': f'{season}-series-{series}',
                'group_path': [season, f'Event-{series % 2}', 'Europe', 'Regional', 'Playoffs', f'Series-{series}'],
                'title': rid, 'date': '2026-01-01T12:00:00Z', 'duration': seconds,
                'rocket_league_id': rid, 'playlist': 'private', 'map': 'stadium_p'}
    return pd.DataFrame(data), index, manifest


def make_rlcs_replay(seed=42, five_codes=False):
    """A complete 300-second regulation, 63-second OT and 2–1 blue win.

    Each post-goal and kickoff interval lasts 90 native frames. Regulation
    includes a full second of zero-clock live play before its OT kickoff.
    Header Goals are deliberately the only goal metadata. Object IDs are
    randomized independently per replay; five_codes adds initialization and
    a second post-goal state, as observed in the 2025 parser output.
    """
    frame, row, manifest = make_replay(seconds=385)
    state = np.full(len(frame), 73, np.float32)
    remaining = np.full(len(frame), 300, np.float32)
    intervals = [(90, 990, 300), (1170, 2070, 270), (2250, 9480, 240)]
    for start, stop, clock in intervals:
        state[start:stop] = 78
        remaining[start:stop] = clock - np.arange(stop - start) // 30
        remaining[stop:] = remaining[stop - 1]
    for start in (990, 2070, 11460):
        state[start:start + 90] = 96
    state[9570:11460] = 78
    remaining[9480:9570] = 0
    remaining[9570:11460] = np.arange(1890) // 30
    remaining[11460:] = 62
    frame['game state'] = state
    frame['seconds remaining'] = remaining
    frame['ball has been hit'] = (state != 73).astype(np.float32)
    frame.loc[state == 73, ['Ball - position x', 'Ball - position y']] = 0
    frame.loc[[989, 2069, 11459], 'Ball - position y'] = [5150, -5215, 5200]
    if five_codes:
        state[0] = 26
        for start in (990, 2070, 11460):
            state[start + 60:start + 90] = 37
    labels = np.unique(state)
    codes = np.random.default_rng(seed).choice(np.arange(10, 250), len(labels), replace=False)
    frame['game state'] = np.select([state == label for label in labels], codes).astype(np.float32)
    meta = json.loads(row['replay_meta'])
    del meta['goals']
    for team, totals in [('team_zero', [1, 1, 0]), ('team_one', [0, 0, 1])]:
        for player, goals in zip(meta[team], totals):
            player['stats']['Goals'] = goals
    row['replay_meta'] = json.dumps(meta)
    return frame, row, manifest


def write_fixture(output: Path, series=4, games=2, seconds=40):
    import pyarrow as pa
    import pyarrow.parquet as pq
    output.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    for season in SEASONS:
        target = output / 'frames' / 'fps30' / season
        target.mkdir(parents=True, exist_ok=True)
        indices = []
        writer = None
        try:
            for s in range(series):
                for game in range(games):
                    frame, row, manifest = make_replay(season, s, game, seconds)
                    table = pa.Table.from_pandas(frame, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(target / 'part-fixture-0.parquet', table.schema)
                    writer.write_table(table, row_group_size=len(frame))
                    indices.append(row)
                    if season != 'rlcs-21-22':
                        manifest_rows.append(manifest)
            odd = dict(indices[0], replay_id=f'{season}-odd', n_players=5, n_frames=0)
            failed = dict(indices[0], replay_id=f'{season}-failed', status='failed', error='synthetic parse failure', n_frames=0)
            indices.extend([odd, failed])
            pq.write_table(pa.Table.from_pandas(pd.DataFrame(indices), preserve_index=False), target / 'part-fixture-0.index.parquet')
        finally:
            if writer is not None:
                writer.close()
    (output / 'manifest').mkdir(exist_ok=True)
    (output / 'manifest' / 'replays.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in manifest_rows))
    (output / 'manifest' / 'groups.jsonl').write_text('')
    (output / 'state-map.synthetic.json').write_text(json.dumps(STATE_MAP, indent=2) + '\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('tests/_synthetic/data'))
    parser.add_argument('--series', type=int, default=4)
    parser.add_argument('--games', type=int, default=2)
    parser.add_argument('--seconds', type=int, default=40)
    args = parser.parse_args()
    print(write_fixture(args.output, args.series, args.games, args.seconds))
