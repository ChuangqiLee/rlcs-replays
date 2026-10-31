"""Local, synthetic contracts for descriptive decomposition, not causal mediation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

MODULE = Path(__file__).resolve().parents[1]/'tactics_code'/'boost_mediation.py'
spec = importlib.util.spec_from_file_location('boost_mediation_under_test', MODULE)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)


def timeline():
    t = np.arange(0., 24.1, .1)
    p = np.zeros((len(t), 6, 8))
    p[:, :3, 6] = 10 + t[:, None] + np.arange(3)*10
    p[:, 3:, 6] = 250
    p[:, 0, 1] = -2000 + 700*t
    p[:, 1, 1] = -500 + 10*t
    p[:, 2, 1] = 800 + 10*t
    p[:, 3:, 1] = 1000 + 10*t[:, None]
    a = {'time': t, 'players': p, 'ball': np.zeros((len(t), 6)),
         'segment': np.zeros(len(t), int), 'live': np.ones(len(t), bool),
         'overtime': np.zeros(len(t)), 'remaining': np.full(len(t), 45.),
         'score_diff': np.zeros(len(t)), 'frame': np.arange(len(t)),
         'touch': np.full(len(t), -1, dtype=np.int8)}
    replay = {'replay_id': 'fixture', 'validated': True, 'observed_start_time': 0.,
              'observed_end_time': t[-1], 'terminal_verified': False,
              'terminal_time': None, 'gap_start_times': '[]', 'gap_end_times': '[]'}
    goals = pd.DataFrame({'replay_id': [], 'time': [], 'scoring_team': [], 'frame': []})
    return a, replay, goals


def anchors_fixture():
    from tactics_code.pushup_dr_tests import _fixture
    df = _fixture(bm.dr, .05)
    df['season'] = np.where(df['split'] == 'train', bm.dr.TRAIN_SEASONS[0], bm.dr.VAL_SEASON)
    df['last_touch_team'] = 'none'
    df['ball_vy_attack'] = df['ball_vy']
    df['ball_in_opp_half'] = df['ball_y'] > 0
    df['boost_t3_raw'] = 80 + 5*(df['displacement_1s'] > 0) + np.random.default_rng(91).uniform(-15, 15, len(df))
    df['boost_status'] = 'observed'
    df['concede20'] = df['y10'].eq(2).astype(float)
    df[bm.BOOST_COLUMNS] = 255.
    df['population'] = 'late_trailing'
    return df


class BoostMediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.threads = threadpool_limits(limits=1)

    @classmethod
    def tearDownClass(cls):
        cls.threads.restore_original_limits()

    def test_synthetic_known_a_b_full_registered_bootstrap(self):
        report = bm.self_test()
        self.assertEqual(report['bootstrap']['repeats'], bm.BOOTSTRAP)
        self.assertEqual(report['bootstrap']['seed'], bm.SEED)
        for name in ('a', 'b'):
            self.assertLessEqual(abs(report['metrics'][name]['estimate']-report['known_coefficients'][name]),
                                 report['recovery_tolerances'][name])

    def test_exact_binary_cell_fixture_recovers_known_coefficients(self):
        # Every A/X/boost-noise cell contains its exact conditional binary mean.
        # This independently checks algebra without Monte Carlo recovery tolerance.
        from itertools import product
        values = []
        known = bm.synthetic_fixture()[-1]
        cell_size = 1000
        for a, x, noise in product((0, 1), (-1, 1), (-10, 10)):
            m = 40+known['a']*a+3*x+noise
            probability = .30+known['direct']*a+known['b']*(m-40)+.04*x
            successes = round(probability*cell_size)
            self.assertAlmostEqual(successes/cell_size, probability)
            for i in range(cell_size):
                values.append((a, m, int(i < successes), x, i//50))
        data = np.asarray(values)
        report, _ = bm.fit_decomposition(data[:, 0], data[:, 1], data[:, 2], data[:, 3:4], data[:, 4], repeats=8)
        for key in ('a', 'b', 'direct'):
            self.assertAlmostEqual(report['metrics'][key]['estimate'], known[key], places=9)

    def test_whole_series_refits_match_explicit_duplicate_rows(self):
        a, m, y, x, _, _ = bm.synthetic_fixture()
        n = 400
        # Unequal cluster sizes distinguish equal-series from equal-row weighting.
        series = np.repeat(np.arange(4), [40, 60, 100, 200])
        report, draws = bm.fit_decomposition(a[:n], m[:n], y[:n], x[:n], series, repeats=8)
        rng = np.random.default_rng(bm.SEED)
        c = np.column_stack([np.ones(n), x[:n], a[:n]])
        for actual in draws:
            sampled = rng.integers(4, size=4)
            idx = np.concatenate([np.flatnonzero(series == s) for s in sampled])
            weights = np.concatenate([np.full(np.sum(series == s), 1/np.sum(series == s)) for s in sampled])
            sw = np.sqrt(weights)
            aa = np.linalg.lstsq(c[idx]*sw[:, None], m[idx]*sw, rcond=None)[0][-1]
            yy = np.column_stack([c[idx], m[idx]])
            fitted = np.linalg.lstsq(yy*sw[:, None], y[idx]*sw, rcond=None)[0]
            total = np.linalg.lstsq(c[idx]*sw[:, None], y[idx]*sw, rcond=None)[0][-1]
            expected = [aa, fitted[-1], aa*fitted[-1], fitted[-2], total, aa*fitted[-1]/total]
            np.testing.assert_allclose(actual, expected, atol=1e-8)
        self.assertEqual(report['series'], len(np.unique(series)))

    def test_cr1_matches_independent_weighted_cluster_sandwich(self):
        import statsmodels.api as sm
        from statsmodels.stats.sandwich_covariance import cov_cluster
        a, m, y, x, series, _ = bm.synthetic_fixture()
        report, _ = bm.fit_decomposition(a, m, y, x, series, repeats=2)
        c = np.column_stack([np.ones(len(a)), x, a])
        weights = 1/pd.Series(series).map(pd.Series(series).value_counts()).to_numpy()
        for response, design, mapping in ((m, c, {'a': -1}),
                                           (y, np.column_stack([c, m]), {'b': -1, 'direct': -2}),
                                           (y, c, {'total': -1})):
            fitted = sm.WLS(response, design, weights=weights).fit()
            se = np.sqrt(np.diag(cov_cluster(fitted, series)))
            for key, index in mapping.items():
                self.assertAlmostEqual(report['metrics'][key]['cr1_se'], se[index], places=9)

    def test_redundant_controls_readonly_and_determinism(self):
        a, m, y, x, series, _ = bm.synthetic_fixture()
        redundant = np.column_stack([x, x[:, 0], np.ones(len(x))])
        for value in (a, m, y, redundant, series):
            value.setflags(write=False)
        r, d = bm.fit_decomposition(a, m, y, redundant, series, repeats=10)
        _, expected = bm.fit_decomposition(a, m, y, x, series, repeats=10)
        np.testing.assert_allclose(d, expected, atol=1e-9)
        self.assertEqual(r['redundant_control_columns'], redundant.shape[1]-x.shape[1])

    def test_unidentified_indicator_and_boost_refused(self):
        a, m, y, x, series, _ = bm.synthetic_fixture()
        with self.assertRaisesRegex(ValueError, 'Indicator'):
            bm.fit_decomposition(np.zeros(len(a)), m, y, x, series, repeats=2)
        with self.assertRaisesRegex(ValueError, 'Boost'):
            bm.fit_decomposition(a, a*2., y, x, series, repeats=2)

    def test_zero_total_proportion_is_undefined(self):
        a, m, y, x, series, _ = bm.synthetic_fixture()
        r, _ = bm.fit_decomposition(a, m, np.zeros(len(y)), x, series, repeats=4)
        self.assertTrue(np.isnan(r['metrics']['proportion']['estimate']))
        self.assertIsNone(r['metrics']['proportion']['bootstrap_ci95'])

    def test_missing_arm_bootstrap_draws_suppress_interval(self):
        rng = np.random.default_rng(bm.SEED)
        series = np.repeat([0, 1], 40)
        a = series.astype(float)
        m = rng.normal(size=len(a))+a
        y = rng.binomial(1, .5, len(a))
        report, draws = bm.fit_decomposition(a, m, y, np.empty((len(a), 0)), series, repeats=20)
        self.assertTrue(report['bootstrap']['invalid_draws'])
        self.assertIsNone(report['metrics']['a']['bootstrap_ci95'])
        self.assertEqual(report['metrics']['a']['status'], 'incomplete_bootstrap')

    def test_endpoint_own_team_interpolation_and_readonly(self):
        a, replay, goals = timeline()
        a['time'] = a['time'] + np.linspace(0, .03, len(a['time']))
        for value in a.values():
            value.setflags(write=False)
        values, status = bm.future_team_boost(a, [0], goals, replay)
        expected = np.interp(bm.BOOST_DELAY, a['time'], a['players'][:, :3, 6].mean(axis=1))
        self.assertAlmostEqual(values[0], expected)
        self.assertEqual(status, ['observed'])

    def test_mediator_missing_rules_and_goal_boundary(self):
        a, replay, goals = timeline()
        for change in ('segment', 'live', 'nan', 'demo', 'gap'):
            b = {k: v.copy() for k, v in a.items()}
            rp = dict(replay)
            if change == 'segment': b['segment'][15:] = 1
            if change == 'live': b['live'][15] = False
            if change == 'nan': b['players'][30, 1, 6] = np.nan
            if change == 'demo': b['players'][30, 1, 7] = 1
            if change == 'gap': rp.update(gap_start_times='[1.1]', gap_end_times='[1.9]')
            self.assertTrue(np.isnan(bm.future_team_boost(b, [0], goals, rp)[0][0]), change)
        for when, observed in ((0., True), (bm.BOOST_DELAY, False), (bm.BOOST_DELAY+.1, True)):
            gg = pd.DataFrame({'time': [when], 'scoring_team': [0]})
            self.assertEqual(np.isfinite(bm.future_team_boost(a, [0], gg, replay)[0][0]), observed)
        self.assertTrue(np.isnan(bm.future_team_boost(a, [len(a['time'])-1], goals, replay)[0][0]))

    def test_concede_any_opponent_goal_endpoints_terminal_and_gaps(self):
        _, replay, _ = timeline()
        goals = pd.DataFrame({'time': [0., 4., 20., 20.1], 'scoring_team': [1, 0, 1, 1]})
        self.assertEqual(bm.concede_labels([0.], 0, goals, replay)[0], 1.)
        only_own = goals.iloc[[0, 1, 3]]
        self.assertEqual(bm.concede_labels([0.], 0, only_own, replay)[0], 0.)
        short = dict(replay, observed_end_time=10.)
        self.assertTrue(np.isnan(bm.concede_labels([0.], 0, only_own.iloc[:2], short)[0]))
        ended = dict(short, terminal_verified=True, terminal_time=10.)
        self.assertEqual(bm.concede_labels([0.], 0, only_own.iloc[:2], ended)[0], 0.)
        gap = dict(replay, gap_start_times='[5]', gap_end_times='[6]')
        self.assertTrue(np.isnan(bm.concede_labels([0.], 0, only_own, gap)[0]))
        self.assertEqual(bm.concede_labels([0.], 0, goals, gap)[0], 1.)

    def test_scale_train_only_255_100_ambiguity_and_validation_range(self):
        df = anchors_fixture()
        for scale in (255., 100.):
            candidate = df.copy()
            candidate[bm.BOOST_COLUMNS] = scale
            got, audit = bm.freeze_boost_scale(candidate)
            self.assertEqual(got, scale)
            self.assertEqual(audit['fit_split'], 'train')
            self.assertAlmostEqual(bm.normalize_boost(candidate, scale)['boost_t3'].iloc[0],
                                   candidate['boost_t3_raw'].iloc[0]*100/scale)
        df.loc[df['split'] == 'val', bm.BOOST_COLUMNS] = 1000
        self.assertEqual(bm.freeze_boost_scale(df)[0], 255.)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            bm.normalize_boost(df, 255.)
        df[bm.BOOST_COLUMNS] = 80
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            bm.freeze_boost_scale(df)

    def test_threshold_parity_and_no_future_selection_in_training(self):
        df = anchors_fixture()
        assigned, original = bm.dr.freeze_initiation(df, delta=bm.dr.DEFAULT_DELTA, control='third', include_early=False)
        changed = df.copy()
        changed.loc[changed['split'] == 'val', 'last_man_y_own'] = -999999
        changed['boost_t3_raw'] = np.nan
        changed['concede20'] = np.nan
        _, frozen = bm.dr.freeze_initiation(changed, delta=bm.dr.DEFAULT_DELTA, control='third', include_early=False)
        self.assertEqual(original['bins'], frozen['bins'])
        again, _ = bm.dr.freeze_initiation(bm.normalize_boost(df, 255.), delta=bm.dr.DEFAULT_DELTA, control='third', include_early=False)
        pd.testing.assert_series_equal(assigned['treatment'], again['treatment'])

    def test_guard_rejects_before_read_and_symlink(self):
        for row in ({'season': 'rlcs-2026', 'split': 'test'},
                    {'season': 'rlcs-2025', 'split': 'train'},
                    {'season': 'rlcs-2024', 'split': 'val'}):
            with patch.object(bm.dr, 'read_slice') as read:
                with self.assertRaises(ValueError):
                    bm.anchor_shard('unused', [row], None, None, None, True, None)
                read.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory)/'alias'
            alias.symlink_to(Path(directory)/'rlcs-2026')
            with self.assertRaises(ValueError): bm.dr.guard_path(alias)

    def test_shard_reader_matches_possession_anchor_and_handles_readonly(self):
        a, replay, goals = timeline()
        with tempfile.TemporaryDirectory() as directory:
            shard = Path(directory)/'compact-fixture.npz'
            np.savez(shard, **a)
            meta = {'season': bm.dr.TRAIN_SEASONS[0], 'split': 'train', '_shard': str(shard),
                    'start': 0, 'stop': len(a['time']), 'series_id': 'series-fixture',
                    'replay_id': 'fixture', 'focal_team': 0, 'region': 'fixture',
                    'player_ids': [str(i) for i in range(6)]}
            expected, _ = bm.dr.anchors_for_replay(meta, a, goals, replay, bm.SEED, design='initiation')
            for smoke in (True, False):
                chunks, audit = bm.anchor_shard(str(shard), [meta], goals, {'fixture': replay}, directory, smoke, None)
                self.assertEqual(len(chunks), 1)
                actual = chunks[0]
                pd.testing.assert_frame_equal(actual[expected.columns], expected)
                self.assertGreater(audit['eligible_anchors'], 0)
                np.testing.assert_allclose(actual['boost_t3_raw'].dropna(),
                                           20 + actual.loc[actual['boost_t3_raw'].notna(), 'state_time'] + bm.BOOST_DELAY)

    def test_analyze_fits_only_validation_and_exact_possession_features(self):
        df = anchors_fixture()
        captured = {}
        def capture(a, m, y, x, series):
            captured.update(x=x, series=set(series), n=len(a))
            return {'label': bm.LABEL}, np.empty((0, len(bm.METRICS)))
        with patch.object(bm, 'fit_decomposition', side_effect=capture):
            report, assigned, _ = bm.analyze(df)
        self.assertEqual(report['feature_names'], bm.possession.feature_matrix(df, df['split'].eq('train').to_numpy())[1])
        self.assertTrue(captured['series'] <= set(df.loc[df['split'] == 'val', 'series_id']))
        self.assertFalse(captured['series'] & set(df.loc[df['split'] == 'train', 'series_id']))
        self.assertGreater(captured['n'], 0)
        self.assertEqual(report['row_audit']['complete_cases'], captured['n'])

    def test_complete_synthetic_analysis(self):
        df = anchors_fixture()
        report, assigned, draws = bm.analyze(df)
        self.assertEqual(report['split'], 'val')
        self.assertEqual(report['season'], bm.dr.VAL_SEASON)
        self.assertEqual(draws.shape, (bm.BOOTSTRAP, len(bm.METRICS)))
        self.assertEqual(report['row_audit']['complete_cases'], report['rows'])
        self.assertEqual(report['metrics']['a']['valid_bootstrap_replicates'], bm.BOOTSTRAP)
        point = {k: v['estimate'] for k, v in report['metrics'].items()}
        self.assertAlmostEqual(point['direct']+point['a*b'], point['total'])
        forbidden = df.copy()
        forbidden.loc[0, 'season'] = 'rlcs-2026'
        with self.assertRaises(ValueError): bm.analyze(forbidden)


if __name__ == '__main__':
    unittest.main()
