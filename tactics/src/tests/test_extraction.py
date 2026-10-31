"""Numerical extraction tests run without requiring an Arrow installation."""
import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tactics_code.data import (frame_goals, goal_agreement, goal_totals, group_metadata,
                               load_state_map, parsed_json, roster_key, stable_player_id, timed_goals)
from tactics_code.extract import (candidate_touches, extract_replay, live_and_context,
                                  role_ranks, segment_ids, select_replays)
from tests.synthetic import make_replay, make_rlcs_replay, STATE_MAP


def replay(**kwargs):
    df, row, item = make_replay(**kwargs)
    return df, row, {item['id']: item}


def test_fixture_uses_real_column_names():
    df, _, _ = replay()
    schema = Path('ctx/schema.txt').read_text()
    literal = next(line[8:] for line in schema.splitlines() if line.startswith('COLUMNS '))
    assert set(df.columns) == set(ast.literal_eval(literal))
    assert df['p0 - boost level (raw replay units)'].dtype == np.float32


def test_perspective_rotates_xy_and_reorders_players():
    df, row, manifest = replay()
    blue, orange = extract_replay(df, row, manifest, {}, STATE_MAP)
    b, o = blue[1], orange[1]
    np.testing.assert_allclose(b['ball'][:, [0, 1, 3, 4]], -o['ball'][:, [0, 1, 3, 4]])
    np.testing.assert_allclose(b['ball'][:, [2, 5]], o['ball'][:, [2, 5]])
    np.testing.assert_allclose(b['players'][:, :3, [0, 1, 3, 4]], -o['players'][:, 3:, [0, 1, 3, 4]], equal_nan=True)
    np.testing.assert_allclose(b['score_diff'], -o['score_diff'])
    assert len(b['time']) == len(df) // 3
    assert blue[0]['roster_id'] == orange[0]['opponent_roster_id']
    assert blue[0]['team_id'] is None


def test_goal_score_strictly_before_prediction_frame():
    df, row, manifest = replay()
    meta = json.loads(row['replay_meta'])
    meta['goals'] = [{'frame': 300, 'team': 0}]
    row['replay_meta'] = json.dumps(meta)
    arrays = extract_replay(df, row, manifest, {}, STATE_MAP)[0][1]
    assert arrays['score_diff'][arrays['frame'] == 300] == 0
    assert arrays['score_diff'][arrays['frame'] == 303] == 1
    assert not arrays['live'][arrays['frame'] == 300]
    before = arrays['segment'][arrays['frame'] == 297][0]
    after = arrays['segment'][arrays['frame'] == 303][0]
    assert before != after


def test_header_goal_totals_do_not_invent_tied_scores():
    df, row, manifest = replay()
    meta = json.loads(row['replay_meta'])
    del meta['goals']
    row['replay_meta'] = json.dumps(meta)
    arrays = extract_replay(df, row, manifest, {}, STATE_MAP)[0][1]
    assert np.isnan(arrays['score_diff']).all()
    assert timed_goals(meta)[0] is None


def test_incomplete_goal_list_is_unknown():
    _, row, _ = replay()
    meta = json.loads(row['replay_meta'])
    meta['goals'] = []
    assert timed_goals(meta) == (None, 'goal_list_disagrees_with_header_totals')
    assert timed_goals({'goals': []}) == ([], 'explicit_complete_goal_list')
    assert timed_goals({'goals': [{'frame': 4, 'team': 'blue'}]})[0] is None


def test_live_and_ot_require_explicit_mapping():
    df, row, manifest = replay(series=3)
    with pytest.raises(ValueError, match='state-map'):
        extract_replay(df, row, manifest, {}, {})
    arrays = extract_replay(df, row, manifest, {}, STATE_MAP)[0][1]
    assert np.all(arrays['overtime'][arrays['game_state'] == 4] == 1)
    assert np.all(arrays['overtime'][arrays['game_state'] == 1] == 0)
    assert not np.any(arrays['live'][np.isin(arrays['game_state'], [0, 3])])
    no_ot_map = extract_replay(df, row, manifest, {}, {'live_states': [1, 4]})[0][1]
    assert np.isnan(no_ot_map['overtime']).all()


def test_missing_car_keeps_3v3_game_and_uncertain_role():
    df, row, manifest = replay()
    outputs = extract_replay(df, row, manifest, {}, STATE_MAP)
    assert len(outputs) == 2
    arrays = outputs[0][1]
    index = np.flatnonzero(arrays['frame'] == 45)[0]
    assert arrays['roles'][index, 2] == -1
    assert arrays['role_uncertain'][index]
    assert arrays['live'][index]


def test_hysteresis_requires_margin_and_sustained_time():
    time = np.arange(8) / 10
    players = np.zeros((8, 3, 3))
    players[:, :, 0] = [100, 300, 600]
    players[1:, 0, 0] = 450
    ball = np.zeros((8, 3))
    roles, _ = role_ranks(players, ball, time, np.ones(8, bool), margin=100, hold=.3)
    assert roles[3, 0] == 0
    assert roles[4, 1] == 0
    # A tiny advantage should never reorder.
    players[:, 0, 0] = 350
    players[0, 0, 0] = 100
    roles, _ = role_ranks(players, ball, time, np.ones(8, bool), margin=100, hold=.1)
    assert (roles[:, 0] == 0).all()


def test_segments_break_on_gap_and_dead_play():
    live = np.array([True, True, False, True, True, True])
    time = np.array([0, .1, .2, .3, .4, 2.0])
    frame = np.arange(6)
    np.testing.assert_array_equal(segment_ids(live, time, frame, 10), [0, 0, -1, 1, 1, 2])


def test_hit_latch_is_not_touch_pulse():
    n = 30
    time = np.arange(n) / 30
    ball = np.zeros((n, 6))
    ball[:, 2] = 500
    players = np.zeros((n, 6, 8))
    players[:, :, :3] = [3000, 3000, 500]
    players[:, 0, :3] = [100, 0, 500]
    hit = np.ones(n)
    assert (candidate_touches(ball, players, time, hit, np.ones(n, bool)) == -1).all()
    ball[12:, 3] = 500
    touches = candidate_touches(ball, players, time, hit, np.ones(n, bool))
    assert np.count_nonzero(touches >= 0) == 1
    players[:, 1, :3] = players[:, 0, :3]
    assert (candidate_touches(ball, players, time, hit, np.ones(n, bool)) == -1).all()


def test_unknown_demolition_stays_unknown_raw_preserved():
    df, row, manifest = replay()
    config = {'live_states': [1]}
    arrays = extract_replay(df, row, manifest, {}, config)[0][1]
    assert np.isnan(arrays['players'][:, :, 7]).all()
    assert (arrays['demolished_raw'] == -1).all()
    arrays = extract_replay(df, row, manifest, {}, STATE_MAP)[0][1]
    assert (arrays['players'][:, :, 7] == 0).all()


def test_ids_and_group_path_fallback_are_explicit():
    _, row, manifest = replay(season='rlcs-21-22')
    group = group_metadata(row, {}, {})
    assert group['series_source'] == 'kaggle_folder_path'
    assert 'Series-0' in group['series_id']
    row['source_file'] = 'batch-0.tar'
    assert group_metadata(row, {}, {})['series_id'] is None
    assert stable_player_id({'name': 'same name'}) is None
    assert stable_player_id({'remote_id': {'Steam': '123'}}) == 'Steam:123'
    assert roster_key(['a', 'b', 'c']) == roster_key(['c', 'b', 'a'])
    assert roster_key(['a', None, 'b']) is None


def test_sample_is_per_season_reproducible_and_duplicate_safe():
    rows = [replay(season=s, series=i)[1] for s in ['rlcs-2024', 'rlcs-2025'] for i in range(7)]
    df = pd.DataFrame(rows)
    first = select_replays(df, 3, 42)
    second = select_replays(df.sample(frac=1), 3, 42)
    assert first['replay_id'].tolist() == second['replay_id'].tolist()
    assert first.groupby('season').size().tolist() == [3, 3]
    with pytest.raises(ValueError, match='Duplicate'):
        select_replays(pd.concat([df, df.iloc[:1]]), 3, 42)


def test_fps_must_subsample_native_exactly():
    df, row, manifest = replay()
    with pytest.raises(ValueError, match='divide'):
        extract_replay(df, row, manifest, {}, STATE_MAP, fps=7)


def test_sampling_preserves_complete_known_series():
    rows, manifest = [], {}
    for series in range(5):
        for game in range(2):
            _, row, item = make_replay(series=series, game=game)
            rows.append(row)
            manifest[item['id']] = item
    selected = select_replays(pd.DataFrame(rows), 5, 42, manifest, {})
    assert len(selected) == 4
    memberships = [manifest[r]['group'] for r in selected['replay_id']]
    assert sorted(pd.Series(memberships).value_counts()) == [2, 2]
    # Source-file fallback and staged manifest produce identical choices when
    # the original manifest is passed through intact.
    staged = select_replays(pd.DataFrame(rows).iloc[::-1], 5, 42, manifest, {})
    assert selected['replay_id'].tolist() == staged['replay_id'].tolist()


def test_subsampling_never_assigns_a_future_touch():
    df, row, manifest = replay()
    for axis, value in zip('xyz', [0, 0, 500]):
        df[f'Ball - position {axis}'] = value
    for axis in 'xyz':
        df[f'Ball - linear velocity {axis}'] = 0.
    for player in range(6):
        df[f'p{player} - position x'] = 3000.
        df[f'p{player} - position y'] = 3000.
        df[f'p{player} - position z'] = 500.
    df['p0 - position x'] = 1000.
    df['p0 - position y'] = 0.
    # Native contact at frame101 lies after retained99, before retained102.
    df.loc[99:103, 'p0 - position x'] = [240., 150., 100., 150., 240.]
    df.loc[101:, 'Ball - linear velocity x'] = 500.
    arrays = extract_replay(df, row, manifest, {}, STATE_MAP)[0][1]
    assert arrays['touch'][arrays['frame'] == 99] == -1
    assert arrays['touch'][arrays['frame'] == 102] == 0


def test_compact_split_filter_never_opens_heldout_arrays(tmp_path, monkeypatch):
    from tactics_code.data import iter_compact
    shard = tmp_path / 'compact-0000.npz'
    shard.touch()
    shard.with_suffix('.parquet').touch()
    monkeypatch.setattr(pd, 'read_parquet', lambda path: pd.DataFrame([{'split': 'test', 'start': 0, 'stop': 1}]))
    def forbidden(*args, **kwargs):
        raise AssertionError('Held-out NPZ opened during development')
    monkeypatch.setattr(np, 'load', forbidden)
    assert list(iter_compact(tmp_path, splits={'train', 'val'})) == []


def test_decoded_demolition_excludes_stale_finite_position_from_roles():
    df, row, manifest = replay()
    # Actor value zero is a real decoded demolition, not a false boolean.
    df.loc[120:150, 'p0 - player demolished by'] = 0.
    outputs = extract_replay(df, row, manifest, {}, STATE_MAP)
    arrays = outputs[0][1]
    demolished = (arrays['frame'] >= 120) & (arrays['frame'] <= 150)
    assert np.isfinite(arrays['players'][demolished, 0, :3]).all()
    assert (arrays['players'][demolished, 0, 7] == 1).all()
    assert (arrays['roles'][demolished, 0] == -1).all()
    assert arrays['role_uncertain'][demolished].all()
    assert (arrays['roles'][arrays['frame'] == 153, 0] >= 0).all()
    # Opponent perspective retains the same raw coordinates and demolition.
    assert (outputs[1][1]['players'][demolished, 3, 7] == 1).all()


def test_rlcs_frame_goals_and_running_score_from_each_perspective():
    df, row, item = make_rlcs_replay()
    config = load_state_map()
    assert config['live_states'] == [78]
    assert config['kickoff_states'] == [73]
    assert config['goal_replay_states'] == [96]
    meta = json.loads(row['replay_meta'])
    assert timed_goals(meta)[0] is None
    goals, diagnostics = frame_goals(df, config)
    assert goals == [(990., 0, 'frame'), (2070., 1, 'frame'), (11460., 0, 'frame')]
    assert diagnostics['goal_events'] == 3
    assert diagnostics['ambiguous_goals'] == 0
    assert diagnostics['team_counts'] == [2, 1]
    assert goal_totals(meta) == [2, 1]
    assert goal_agreement(goals, meta) is True
    blue, orange = extract_replay(df, row, {item['id']: item}, {}, config)
    for metadata, arrays in (blue, orange):
        assert metadata['state_source'] == 'explicit_state_map'
        assert metadata['score_source'] == 'frame_state_transitions'
        assert np.isfinite(arrays['score_diff']).all()
        assert arrays['live'].sum() > 3000
    b, o = blue[1], orange[1]
    np.testing.assert_array_equal(b['score_diff'], -o['score_diff'])
    for frame, expected in [(987, 0), (990, 0), (993, 1), (2070, 1), (2073, 0),
                            (11460, 0), (11463, 1)]:
        assert b['score_diff'][b['frame'] == frame].item() == expected
    assert not b['live'][np.isin(b['game_state'], [73, 96])].any()


def test_rlcs_overtime_uses_transition_not_reused_code_or_positive_clock():
    df, row, _ = make_rlcs_replay()
    live, overtime, score, source, goals_source, boundaries = live_and_context(
        df, json.loads(row['replay_meta']), load_state_map())
    assert source == 'explicit_state_map'
    assert goals_source == 'frame_state_transitions'
    assert np.all(df['seconds remaining'] == np.floor(df['seconds remaining']))
    assert live[9450:9480].all()  # Zero-clock ball-in-air regulation is still live.
    assert (overtime[9450:9480] == 0).all()
    assert (overtime[live & (df['frame'].to_numpy() < 9480)] == 0).all()
    assert live[9570:11460].all()
    assert (overtime[9570:11460] == 1).all()
    assert (overtime[11460:] == 0).all()  # The golden goal ends OT.
    assert df.loc[11459, 'seconds remaining'] == 62
    assert np.flatnonzero(boundaries).tolist() == [990, 2070, 11460]
    assert score[11461] == 1


def test_rlcs_goal_at_zero_does_not_start_overtime():
    df, row, _ = make_rlcs_replay()
    df.loc[9480:9569, 'game state'] = 96
    df.loc[9479, 'Ball - position y'] = 5150
    _, overtime, _, _, _, _ = live_and_context(df, json.loads(row['replay_meta']), load_state_map())
    assert (overtime[9570:11460] == 0).all()


def test_rlcs_no_goal_replay_has_known_zero_score():
    df, row, _ = make_rlcs_replay()
    df = df.iloc[:990].copy()
    meta = json.loads(row['replay_meta'])
    for team in ('team_zero', 'team_one'):
        for player in meta[team]:
            player['stats']['Goals'] = 0
    goals, diagnostics = frame_goals(df, load_state_map())
    assert goals == []
    assert diagnostics['goal_events'] == 0
    assert goal_agreement(goals, meta) is True
    live, overtime, score, _, source, boundaries = live_and_context(df, meta, load_state_map())
    assert source == 'frame_state_transitions'
    assert (score == 0).all()
    assert (overtime[live] == 0).all()
    assert not boundaries.any()


@pytest.mark.parametrize('ball_y', [5000., -5000., 0., np.nan])
def test_rlcs_ambiguous_goal_does_not_fabricate_scoring_team(ball_y):
    df, row, _ = make_rlcs_replay()
    df.loc[989, 'Ball - position y'] = ball_y
    meta = json.loads(row['replay_meta'])
    goals, diagnostics = frame_goals(df, load_state_map())
    assert goals[0] == (990., None, 'frame')
    assert diagnostics['ambiguous_goals'] == 1
    assert goal_agreement(goals, meta) is False
    live, _, score, _, source, boundaries = live_and_context(df, meta, load_state_map())
    assert source == 'frame_state_transitions'
    assert (score[:991] == 0).all()
    assert np.isnan(score[991:]).all()
    assert boundaries[990]
    assert not live[990]


def test_rlcs_frame_goal_agreement_reports_mismatch_and_missing_totals():
    df, row, _ = make_rlcs_replay()
    goals, _ = frame_goals(df, load_state_map())
    meta = json.loads(row['replay_meta'])
    meta['team_zero'][0]['stats']['Goals'] += 1
    assert goal_totals(meta) == [3, 1]
    assert goal_agreement(goals, meta) is False
    del meta['team_one'][0]['stats']['Goals']
    assert goal_totals(meta) is None
    assert goal_agreement(goals, meta) is None


def test_rlcs_explicit_metadata_timeline_takes_precedence():
    df, row, _ = make_rlcs_replay()
    meta = json.loads(row['replay_meta'])
    meta['goals'] = [{'frame': 900, 'team': 0}, {'frame': 2000, 'team': 1},
                     {'frame': 11000, 'team': 0}]
    _, _, score, _, source, boundaries = live_and_context(df, meta, load_state_map())
    assert source == 'explicit_complete_goal_list'
    assert score[901] == 1
    assert score[2001] == 0
    assert score[11001] == 1
    assert np.flatnonzero(boundaries).tolist() == [900, 2000, 11000]
