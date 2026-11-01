"""Data-free, fixed-seed equivalence checks; no replay files are opened."""
import contextlib
import io
import unittest

import numpy as np
import pandas as pd
from scipy import linalg
from threadpoolctl import threadpool_limits

from tactics_code import boost_mediation as mediation, pushup_dr as dr


ATOL, RTOL = 1e-12, 1e-10


def assert_equivalent(test, left, right):
    if isinstance(left, dict):
        test.assertEqual(set(left), set(right))
        for key in left:
            if key != 'timing_seconds':
                assert_equivalent(test, left[key], right[key])
    elif isinstance(left, np.ndarray):
        np.testing.assert_allclose(left, right, atol=ATOL, rtol=RTOL, equal_nan=True)
    elif isinstance(left, (list, tuple)):
        test.assertEqual(len(left), len(right))
        for old_value, new_value in zip(left, right):
            assert_equivalent(test, old_value, new_value)
    elif isinstance(left, (float, np.floating)):
        np.testing.assert_allclose(left, right, atol=ATOL, rtol=RTOL, equal_nan=True)
    else:
        test.assertEqual(left, right)


class LowmemMediationTests(unittest.TestCase):
    def setUp(self):
        self.limits = threadpool_limits(limits=1)
        self.limits.__enter__()
        self.stderr = contextlib.redirect_stderr(io.StringIO())
        self.stderr.__enter__()

    def tearDown(self):
        self.stderr.__exit__(None, None, None)
        self.limits.__exit__(None, None, None)

    def test_raw_qr_keeps_identical_rank_factorization(self):
        rng = np.random.default_rng(42)
        x = rng.normal(size=(200, 7))
        x = np.column_stack([np.ones(len(x)), x, x[:, 2], np.ones(len(x))])
        _, old_r, old_pivots = linalg.qr(x, mode='economic', pivoting=True, check_finite=False)
        reflectors, new_r, new_pivots = linalg.qr(x, mode='raw', pivoting=True, check_finite=False)
        self.assertEqual(new_r.shape, (x.shape[1], x.shape[1]))
        np.testing.assert_array_equal(old_pivots, new_pivots)
        np.testing.assert_array_equal(old_r, new_r)
        del reflectors
        # Exercise both sides of the unchanged relative rank cutoff.
        basis, _ = np.linalg.qr(rng.normal(size=(200, 3)))
        for small, expected_rank in ((.5e-10, 2), (2e-10, 3)):
            near_rank_boundary = basis*np.array([1., .5, small])
            _, old_r, old_pivots = linalg.qr(near_rank_boundary, mode='economic', pivoting=True)
            reflectors, new_r, new_pivots = linalg.qr(near_rank_boundary, mode='raw', pivoting=True)
            np.testing.assert_array_equal(old_r, new_r)
            np.testing.assert_array_equal(old_pivots, new_pivots)
            rank = np.count_nonzero(np.abs(np.diag(new_r)) > np.abs(new_r[0, 0])*1e-10)
            self.assertEqual(rank, expected_rank)
            del reflectors

    def test_all_registered_draws_with_redundant_controls(self):
        a, m, y, x, series, _ = mediation.synthetic_fixture()
        x = np.column_stack([x, x[:, 0], np.ones(len(x)), np.zeros(len(x))])
        old, old_draws = mediation.fit_decomposition(a, m, y, x, series)
        new, new_draws = mediation.fit_decomposition(a, m, y, x, series, lowmem=True)
        self.assertEqual(old_draws.shape, (2000, 6))
        assert_equivalent(self, old, new)
        np.testing.assert_array_equal(old['retained_control_indices_including_intercept'],
                                      new['retained_control_indices_including_intercept'])
        np.testing.assert_allclose(old_draws, new_draws, atol=ATOL, rtol=RTOL, equal_nan=True)

    def test_support_and_input_failures_are_unchanged(self):
        a, m, y, x, series, _ = mediation.synthetic_fixture()
        cases = [(np.ones_like(a), m, y, x, series),
                 (a, a.astype(float), y, x, series),
                 (a, m, y, x, np.zeros_like(series))]
        bad = x.copy()
        bad[0, 0] = np.nan
        cases.append((a, m, y, bad, series))
        for values in cases:
            errors = []
            for enabled in (False, True):
                with self.assertRaises(ValueError) as error:
                    mediation.fit_decomposition(*values, lowmem=enabled)
                errors.append(str(error.exception))
            self.assertEqual(*errors)

    def test_full_analysis_training_vocabulary_and_complete_case_selection(self):
        rng = np.random.default_rng(42)
        count, per_series = 18, 60
        n = count*per_series
        frame = pd.DataFrame(rng.normal(size=(n, len(dr.NUMERIC_FEATURES))), columns=dr.NUMERIC_FEATURES)
        series = np.repeat(np.arange(count), per_series)
        train = series < 6
        frame['series_id'] = ['series-' + str(i) for i in series]
        frame['split'] = np.where(train, 'train', 'val')
        frame['season'] = np.where(train, dr.TRAIN_SEASONS[0], dr.VAL_SEASON)
        frame['region'] = np.where(np.arange(n) % 2, 'a', 'b')
        frame['last_man_id'] = np.where(np.arange(n) % 3, 'player-a', 'player-b')
        frame.loc[n-1, 'last_man_id'] = 'validation-only'
        frame['last_man_y_own'] = rng.uniform(-1000, 1000, n)
        frame['last_man_behind_ball'] = rng.normal(size=n)
        frame['ball_bin'] = np.arange(n) % 4
        frame['baseline_goal_side'] = True
        frame['displacement_1s'] = np.where(rng.binomial(1, .5, n), 600., 0.)
        frame['early_goal'] = False
        frame['last_touch_team'] = np.resize(['own', 'opponent', 'none'], n)
        frame['ball_vy_attack'] = frame['ball_vy'].copy()
        frame['ball_in_opp_half'] = frame['ball_y'] > 0
        frame['population'] = 'late_trailing'
        frame['boost_status'] = 'observed'
        for column in mediation.BOOST_COLUMNS:
            frame[column] = rng.uniform(0, 255, n)
            frame.loc[[0, per_series], column] = 255.
        frame['boost_t3_raw'] = rng.uniform(10, 240, n)
        frame['concede20'] = rng.binomial(1, .2, n).astype(float)
        frame.loc[n-5, 'boost_t3_raw'] = np.nan
        frame.loc[n-4, 'concede20'] = np.nan
        original = frame.copy(deep=True)
        old, old_assigned, old_draws = mediation.analyze(frame)
        new, new_assigned, new_draws = mediation.analyze(frame, lowmem=True)
        pd.testing.assert_frame_equal(frame, original, check_exact=True)
        pd.testing.assert_frame_equal(old_assigned, new_assigned, check_exact=True)
        assert_equivalent(self, old, new)
        np.testing.assert_allclose(old_draws, new_draws, atol=ATOL, rtol=RTOL, equal_nan=True)
        self.assertEqual(new_draws.shape, (2000, 6))
        self.assertEqual(old['row_audit'], new['row_audit'])


if __name__ == '__main__':
    unittest.main()
