"""Synthetic equivalence checks; no replay data is read."""
import unittest

import numpy as np
import pandas as pd

from tactics_code import lowmem, pushup_dr as dr, pushup_possession as original


def fixture(n=211):
    rng = np.random.default_rng(42)
    df = pd.DataFrame(rng.normal(size=(n, len(dr.NUMERIC_FEATURES))),
                      columns=dr.NUMERIC_FEATURES)
    df['last_man_y_own'] = rng.normal(size=n)
    df['last_man_behind_ball'] = rng.integers(0, 2, size=n).astype(bool)
    df['region'] = np.resize(['west', 'east', 'north'], n)
    df['last_man_id'] = np.resize([f'p{i:02}' for i in range(43)], n)
    df['last_touch_team'] = np.resize(original.TOUCH_LEVELS, n)
    df['ball_vy_attack'] = rng.normal(size=n)
    df['ball_in_opp_half'] = rng.integers(0, 2, size=n).astype(bool)
    train = np.arange(n) < 151
    df.loc[~train, 'region'] = 'validation_only'
    df.loc[~train, 'last_man_id'] = 'validation_only'
    return df, train


class LowmemFeatureTests(unittest.TestCase):
    def test_features_bitwise_and_frozen_vocabulary(self):
        df, train = fixture()
        expected, names, regions = original.feature_matrix(df, train)
        actual, actual_names, actual_regions = lowmem.possession_feature_matrix(df, train)
        self.assertEqual(expected.dtype, actual.dtype)
        self.assertEqual(names, actual_names)
        self.assertEqual(regions, actual_regions)
        self.assertNotIn('region=validation_only', names)
        self.assertNotIn('last_man_id=validation_only', names)
        np.testing.assert_array_equal(expected.view(np.uint32), actual.view(np.uint32))
        frozen = [i for i, name in enumerate(names) if name.startswith(('region=', 'last_man_id='))]
        self.assertFalse(actual[~train][:, frozen].any())

    def test_train_statistics_and_standardization(self):
        df, train = fixture()
        x, _, _ = original.feature_matrix(df, train)
        center = x[train].mean(axis=0, dtype=float)
        spread = x[train].std(axis=0, dtype=float)
        for width in (2, 16, 32, 64):
            actual_center, actual_spread = lowmem.training_moments(x, train, width)
            np.testing.assert_allclose(actual_center, center, atol=1e-12, rtol=1e-10)
            np.testing.assert_allclose(actual_spread, spread, atol=1e-12, rtol=1e-10)
            safe_spread = np.where(spread > 1e-10, spread, 1.)
            expected = ((x-center)/safe_spread)[~train]
            actual = lowmem.standardized_rows(x, ~train, center, safe_spread, width)
            np.testing.assert_array_equal(expected.view(np.uint64), actual.view(np.uint64))

    def test_one_column_and_remainder(self):
        rng = np.random.default_rng(7)
        for columns in (1, 2, 3, 32, 33, 65):
            x = rng.normal(size=(101, columns)).astype(np.float32)
            train = np.arange(len(x)) % 3 != 0
            center, spread = lowmem.training_moments(x, train)
            np.testing.assert_allclose(center, x[train].mean(axis=0, dtype=float), atol=1e-12, rtol=1e-10)
            np.testing.assert_allclose(spread, x[train].std(axis=0, dtype=float), atol=1e-12, rtol=1e-10)

    def test_nonfinite_and_unknown_touch_rejected(self):
        df, train = fixture()
        for column, value, message in (
                ('ball_x', np.nan, 'Nonfinite baseline controls'),
                ('ball_vy_attack', np.inf, 'Nonfinite possession covariates'),
                ('last_touch_team', 'invalid', 'Unknown last_touch_team')):
            bad = df.copy()
            bad.loc[0, column] = value
            with self.assertRaisesRegex(ValueError, message):
                lowmem.possession_feature_matrix(bad, train)


if __name__ == '__main__':
    unittest.main()
