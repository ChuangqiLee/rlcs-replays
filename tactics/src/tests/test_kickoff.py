"""Synthetic P6.2 regression tests; no production data or network required."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tactics_code import kickoff as k
from tactics_code.events import build_replay_events

STATE_MAP = dict(state_decoding='per_replay_decoded', goal_detection='frame_state_transitions',
                 overtime_detection='frame_state_transitions')


def fixture():
    t = np.arange(0., 40.05, .05)
    state = np.where(t < 10, 101, np.where(t < 12, 31, np.where(t < 14, 77, np.where(t < 30, 101, 31))))
    hit = ((t < 10) | ((t >= 15) & (t < 30))).astype(float)
    y = np.zeros(len(t))
    y[np.isclose(t, 9.95)] = 5200
    y[np.isclose(t, 29.95)] = -5200
    frames = pd.DataFrame({'replay_id': 'replay-a', 'frame': np.arange(len(t)), 'current time': t,
                           'seconds remaining': 300-t, 'game state': state,
                           'ball has been hit': hit, 'Ball - position y': y})
    meta = dict(replay_id='replay-a', season=k.VAL, split='val', series_id='series-a', focal_team=0,
                replay_meta={'team_zero': [{'stats': {'Goals': 1}}],
                             'team_one': [{'stats': {'Goals': 1}}]})
    ct = t[::2]
    players = np.zeros((len(ct), 6, 8))
    for player, xy in enumerate(k.SPAWNS[[0, 2, 4]]):
        players[:, player, :2] = xy
        players[:, player+3, :2] = -xy
    players[:, :, 2] = 17
    players[:, :, 6] = 80/100*255
    players[:, :, 7] = np.nan  # duration unverified in real compact
    ball = np.zeros((len(ct), 6))
    ball[:, 2] = 300
    # Non-kicker controlled contact after the kickoff latch onset.
    contact = int(np.flatnonzero(np.isclose(ct, 17))[0])
    players[contact:contact+4, 1, :6] = ball[contact:contact+4]
    players[np.isclose(ct, 16), 2, :2] = k.CORNERS[0]
    players[ct >= 16, 2, 6] = 255
    touch = np.full(len(ct), -1, dtype=int)
    touch[contact] = 1
    a = dict(time=ct, frame=np.arange(len(t))[::2], players=players, ball=ball,
             live=(state == 101)[::2], touch=touch)
    goals, summary = build_replay_events(frames, meta, STATE_MAP)
    return frames, meta, a, goals, summary


def synthetic_units(split='val', n_series=24, per_series=30):
    rng = np.random.default_rng(71 if split == 'val' else 19)
    rows = []
    for g in range(n_series):
        shift = rng.normal(0, 70)
        for i in range(per_series):
            score = (-1, 1)[i % 2]
            depth = rng.normal(0, 400) + shift + (150 if score == -1 else 0)
            rows.append(dict(replay_id=f'{split}-r{g}-{i//2}', series_id=f'{split}-s{g}',
                             kickoff_id=f'{split}-r{g}-{i//2}:100', focal_team=i % 2,
                             split=split, season=k.VAL if split == 'val' else k.TRAIN[g % len(k.TRAIN)],
                             score_diff=score, time_bin=k.TIME_BINS[(i//2) % len(k.TIME_BINS)],
                             spawn=k.SPAWN_NAMES[(i//6) % len(k.SPAWN_NAMES)],
                             depth_at_T=depth, max_depth_window=depth+abs(rng.normal(0, 30)),
                             corner_pad_taken=float(rng.random() < .4),
                             first_possession_focal=float(rng.random() < .5),
                             first_possession_team=i % 2, concede_20s=float(rng.random() < .1)))
    return pd.DataFrame(rows)


class KickoffTests(unittest.TestCase):
    def setUp(self):
        self.frames, self.meta, self.a, self.goals, self.summary = fixture()
        self.starts = k.kickoff_starts(self.frames, self.goals, self.summary)

    def rows(self):
        return k.replay_units(self.a, self.meta, self.starts, self.goals, self.summary)

    def test_post_goal_not_initial_and_replay_local_codes(self):
        self.assertTrue(self.summary['validated'])
        self.assertEqual(len(self.starts), 1)
        self.assertAlmostEqual(self.starts[0]['start_time'], 14)
        altered = self.frames.copy()
        altered['game state'] = altered['game state'].map({101: 991, 31: 123, 77: 456})
        goals, summary = build_replay_events(altered, self.meta, STATE_MAP)
        self.assertEqual(self.starts, k.kickoff_starts(altered, goals, summary))

    def test_kicker_spawn_fixed_non_kickers_rotation_and_T(self):
        blue, orange = self.rows()
        self.assertEqual([blue['kicker'], orange['kicker']], [0, 3])
        self.assertEqual([blue['spawn'], orange['spawn']], ['diagonal_left']*2)
        self.assertEqual(json.loads(blue['nonkickers']), [1, 2])
        self.assertAlmostEqual(blue['T'], 3)
        self.assertAlmostEqual(blue['depth_at_T'], 0)
        self.assertAlmostEqual(orange['depth_at_T'], -3840)
        self.assertEqual([blue['score_diff'], orange['score_diff']], [1, -1])
        self.assertEqual([blue['first_possession_focal'], orange['first_possession_focal']], [1, 0])

    def test_window_max_is_not_endpoint_and_kicker_ignored(self):
        self.a['players'][np.isclose(self.a['time'], 16), 1, 1] = 500
        self.a['players'][np.isclose(self.a['time'], 16), 0, 1] = 4000
        blue = self.rows()[0]
        self.assertEqual(blue['depth_at_T'], 0)
        self.assertEqual(blue['max_depth_window'], 500)

    def test_boost_pickup_and_missing_raw(self):
        blue, orange = self.rows()
        self.assertEqual(blue['corner_pad_taken'], 1)
        self.assertEqual(orange['corner_pad_taken'], 0)
        self.a['players'] = self.a['players'][:, :, :6]
        self.assertTrue(np.isnan(self.rows()[0]['corner_pad_taken']))
        self.assertEqual(self.rows()[0]['boost_status'], 'raw_boost_not_computable')

    def test_kicker_and_small_pad_and_noncorner_do_not_count(self):
        self.a['players'][:, 2, 6] = 255
        j = np.flatnonzero(np.isclose(self.a['time'], 16))[0]
        self.a['players'][j:, 2, 6] = 255
        self.a['players'][j-1, 2, 6] = .9*255
        self.assertEqual(self.rows()[0]['corner_pad_taken'], 0)
        self.a['players'][j-1, 2, 6] = .2*255
        self.a['players'][j, 2, :2] = [0, 0]
        self.assertEqual(self.rows()[0]['corner_pad_taken'], 0)
        self.a['players'][j-1, 0, 6] = .2*255
        self.a['players'][j:, 0, 6] = 255
        self.a['players'][j, 0, :2] = k.CORNERS[0]
        self.assertEqual(self.rows()[0]['corner_pad_taken'], 0)

    def test_first_kicker_touch_does_not_end_window(self):
        self.a['touch'][np.isclose(self.a['time'], 15.5)] = 0
        self.assertAlmostEqual(self.rows()[0]['T'], 3)
        self.a['touch'][:] = -1
        self.assertAlmostEqual(self.rows()[0]['T'], k.WINDOW)
        self.assertTrue(np.isnan(self.rows()[0]['first_possession_focal']))

    def test_uncontrolled_contact_ends_T_but_no_possession(self):
        self.a['players'][np.isclose(self.a['time'], 17.2), 1, 0] = 3000
        blue = self.rows()[0]
        self.assertAlmostEqual(blue['T'], 3)
        self.assertIsNone(blue['first_possession_team'])

    def test_goals_and_followup_censoring(self):
        blue, orange = self.rows()
        self.assertEqual([blue['concede_20s'], orange['concede_20s']], [1, 0])
        short = dict(self.summary, observed_end_time=25)
        self.assertTrue(np.isnan(k.concede_label(14, 1, [], short)[0]))
        terminal = dict(short, terminal_verified=True, terminal_time=24)
        self.assertEqual(k.concede_label(14, 1, [], terminal)[0], 0)
        gap = dict(self.summary, gap_start_times='[20]', gap_end_times='[21]')
        self.assertTrue(np.isnan(k.concede_label(14, 1, [], gap)[0]))
        bracket = [dict(scoring_team=1, time=34.05, last_live_time=33.95)]
        self.assertTrue(np.isnan(k.concede_label(14, 0, bracket, self.summary)[0]))

    def test_unknown_contest_missing_touch_and_early_goal_not_negative(self):
        self.starts[0]['contest_time'] = None
        self.assertTrue(np.isnan(self.rows()[0]['depth_at_T']))
        self.starts[0]['contest_time'] = 15
        del self.a['touch']
        self.assertTrue(np.isnan(self.rows()[0]['depth_at_T']))
        self.a['touch'] = np.full(len(self.a['time']), -1)
        self.starts[0]['live_end_time'] = 16
        self.assertTrue(np.isnan(self.rows()[0]['depth_at_T']))

    def test_invalid_goal_audit_and_overtime_not_units(self):
        self.summary['validated'] = False
        self.assertEqual(k.kickoff_starts(self.frames, self.goals, self.summary), [])
        frames = self.frames.copy()
        frames.loc[frames['current time'] >= 14, 'seconds remaining'] = 0
        goals, summary = build_replay_events(frames, self.meta, STATE_MAP)
        self.assertEqual(k.kickoff_starts(frames, goals, summary), [])

    def test_spawn_tie_and_unknown_spawn(self):
        p, ball = self.a['players'][0].copy(), self.a['ball'][0]
        p[1, :2] = k.SPAWNS[1]
        answer = k.spawn_assignment(p, ball, [0, 1, 2], 1)
        self.assertEqual(answer[0], 0)
        self.assertTrue(answer[3])
        p[:, :2] = 0
        self.assertIsNone(k.spawn_assignment(p, ball, [0, 1, 2], 1)[2])

    def test_train_frozen_and_val_only(self):
        train = synthetic_units('train')
        frozen = k.freeze_thresholds(train)
        expected = np.quantile(train['depth_at_T'], [1/3, 2/3])
        np.testing.assert_allclose(frozen['tercile_edges'], expected)
        with self.assertRaises(ValueError):
            k.freeze_thresholds(synthetic_units('val'))
        with self.assertRaises(ValueError):
            k.analyze(train, frozen)
        changed = dict(frozen, fit_seasons=['rlcs-2026'])
        with self.assertRaises(ValueError):
            k.validate_thresholds(changed)

    def test_series_bootstrap_matches_literal_cluster_resampling(self):
        rng = np.random.default_rng(5)
        x = np.column_stack([np.ones(60), rng.normal(size=60)])
        y = x @ [2, 3] + rng.normal(size=60)
        groups = np.repeat(np.arange(6), 10).astype(str)
        result = k.infer(x, y, groups, {'slope': np.array([0, 1])}, repeats=40)['slope']
        draws = []
        rng = np.random.default_rng(k.SEED)
        for _ in range(40):
            counts = rng.multinomial(6, np.ones(6)/6)
            indices = np.concatenate([np.tile(np.flatnonzero(groups == str(g)), counts[g]) for g in range(6)])
            draws.append(np.linalg.lstsq(x[indices], y[indices], rcond=None)[0][1])
        np.testing.assert_allclose(result['bootstrap_ci'], np.quantile(draws, [.025, .975]))

    def test_cr1_matches_independent_statsmodels_and_rank_failure(self):
        import statsmodels.api as sm
        rng = np.random.default_rng(123)
        x = np.column_stack([np.ones(80), rng.normal(size=80)])
        y = x @ [3, -2] + rng.normal(size=80)
        groups = np.repeat(np.arange(8), 10).astype(str)
        fit = k.infer(x, y, groups, {'slope': np.array([0, 1])}, repeats=40)['slope']
        check = sm.OLS(y, x).fit(cov_type='cluster', cov_kwds={'groups': groups, 'use_correction': True})
        self.assertAlmostEqual(fit['estimate'], check.params[1])
        self.assertAlmostEqual(fit['cr1_se'], check.bse[1])
        bad = k.infer(np.ones((80, 2)), y, groups, {'slope': np.array([0, 1])})['slope']
        self.assertIsNone(bad['estimate'])

    def test_positive_and_null_K1_and_no_validation_threshold_refit(self):
        val, train = synthetic_units(), synthetic_units('train')
        frozen = k.freeze_thresholds(train)
        before = json.dumps(frozen, sort_keys=True)
        result = k.analyze(val, frozen)
        self.assertGreater(result['K1']['pooled']['estimate'], 0)
        self.assertTrue(result['K1']['pooled']['finding'])
        self.assertEqual(result['K1']['pooled']['bootstrap_successful'], k.BOOTSTRAP)
        val['depth_at_T'] = 0.
        null = k.primary(val)['pooled']
        self.assertEqual(null['estimate'], 0.)
        self.assertFalse(null['finding'])
        self.assertEqual(before, json.dumps(frozen, sort_keys=True))

    def test_missing_geometry_and_sampling_gap_retained_as_null(self):
        self.a['players'][np.isclose(self.a['time'], 16), 1, 1] = np.nan
        self.assertTrue(np.isnan(self.rows()[0]['depth_at_T']))
        self.assertEqual(len(self.rows()), 2)
        keep = ~((self.a['time'] > 15) & (self.a['time'] < 16))
        self.a = {key: value[keep] for key, value in self.a.items()}
        self.assertEqual(self.rows()[0]['window_status'], 'window_truncated_or_gap')

    def test_null_outcomes_and_zero_contrast_are_reported(self):
        df = synthetic_units('val')
        df['corner_pad_taken'] = np.nan
        df['concede_20s'] = 0.
        frozen = k.freeze_thresholds(synthetic_units('train'))
        report = k.analyze(df, frozen)
        self.assertEqual(set(report['K2']), set(k.OUTCOMES))
        self.assertIsNone(report['K2']['corner_pad_taken']['adjusted']['high']['estimate'])
        null = report['K2']['concede_20s']['adjusted']['high_minus_low']
        self.assertEqual(null['estimate'], 0)
        self.assertEqual(null['bootstrap_successful'], k.BOOTSTRAP)
        empty = k.analyze(pd.DataFrame(), frozen)
        self.assertFalse(empty['K1']['pooled']['finding'])
        self.assertEqual(empty['status'], 'no_eligible_units')

    def test_guards_before_payload_reads(self):
        for path in ('/tmp/rlcs-2026/compact.npz', '/tmp/test/compact.npz'):
            with self.assertRaises(ValueError):
                k.guard_path(path)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'artifacts') as temp:
            root = Path(temp)
            (root / 'val').mkdir()
            (root / 'rlcs-2026').mkdir()
            (root / 'allowed').symlink_to(root / 'rlcs-2026', target_is_directory=True)
            with self.assertRaises(ValueError):
                k.guard_path(root / 'allowed')
            bad = dict(self.meta, season='rlcs-2026', split='test')
            with patch.object(k.np, 'load', side_effect=AssertionError('must not open arrays')):
                with self.assertRaises(ValueError):
                    k.replay_units({}, bad, [], [], {})

    def test_end_to_end_local_cli(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'artifacts') as temp:
            root = Path(temp)
            compact, native, out = root/'compact', root/'native', root/'out'
            (compact/k.VAL).mkdir(parents=True)
            (native/'frames'/'fps30'/k.VAL).mkdir(parents=True)
            pair = []
            for team in (0, 1):
                pair.append(dict(self.meta, replay_meta=json.dumps(self.meta['replay_meta']),
                                 focal_team=team, start=0, stop=len(self.a['time']),
                                 state_decoding='per_replay_decoded'))
            pd.DataFrame(pair).to_parquet(compact/k.VAL/'compact-0000.parquet')
            np.savez_compressed(compact/k.VAL/'compact-0000.npz', **self.a)
            native_path = native/'frames'/'fps30'/k.VAL/'frames.parquet'
            self.frames.to_parquet(native_path, row_group_size=len(self.frames), index=False)
            pd.DataFrame([dict(self.meta, replay_meta=json.dumps(self.meta['replay_meta']))]).to_parquet(
                native_path.with_name('frames.index.parquet'), index=False)
            state_map = root/'state_map.json'
            state_map.write_text(json.dumps(STATE_MAP))
            thresholds = root/'thresholds.json'
            thresholds.write_text(json.dumps(k.freeze_thresholds(synthetic_units('train'))))
            # A poison test directory must never be enumerated or opened.
            (compact/'rlcs-2026').mkdir()
            (compact/'rlcs-2026'/'compact-0000.parquet').write_text('must not read')
            k.main(['--compact', str(compact), '--data-root', str(native), '--state-map', str(state_map),
                    '--output', str(out), '--thresholds', str(thresholds)])
            result = json.loads((out/'results'/'p6_kickoff.json').read_text())
            self.assertEqual(result['n_units'], 2)
            self.assertFalse(result['test_season_opened'])
            self.assertEqual(result['outcomes']['corner_pad_taken']['n_observed'], 2)
            self.assertTrue((out/'artifacts'/'p6_kickoff'/'val'/'kickoff_units.parquet').exists())
            # Exercise the normal TRAIN-freeze-before-VAL path as well.
            train_season = k.TRAIN[0]
            (compact/train_season).mkdir()
            train_native = native/'frames'/'fps30'/train_season
            train_native.mkdir()
            train_pair = [dict(row, replay_id='train-r', series_id='train-s', split='train',
                               season=train_season) for row in pair]
            pd.DataFrame(train_pair).to_parquet(compact/train_season/'compact-0000.parquet')
            np.savez_compressed(compact/train_season/'compact-0000.npz', **self.a)
            self.frames.assign(replay_id='train-r').to_parquet(train_native/'frames.parquet',
                row_group_size=len(self.frames), index=False)
            pd.DataFrame([train_pair[0]]).to_parquet(train_native/'frames.index.parquet', index=False)
            k.main(['--compact', str(compact), '--data-root', str(native), '--state-map', str(state_map),
                    '--output', str(root/'out-freeze')])
            frozen = json.loads((root/'out-freeze'/'artifacts'/'p6_kickoff'/'train_thresholds.json').read_text())
            self.assertEqual(frozen['fit_seasons'], [train_season])
            self.assertEqual(frozen['n_train_units'], len(self.rows()))


if __name__ == '__main__':
    unittest.main()
