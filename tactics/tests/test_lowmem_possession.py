"""Synthetic P4 low-memory equivalence; no replay files are read.

Run with OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1.
Production iterations, folds, bootstrap repeats, trim and seeds stay unchanged.
"""
from __future__ import annotations

import numbers
import unittest

import numpy as np

from tactics_code import pushup_dr as dr
from tactics_code import pushup_possession as possession
from tactics_code.pushup_dr_tests import _fixture


RTOL, ATOL = 1e-10, 1e-12


def possession_fixture(rows_per_series=None):
    frame = _fixture(dr, effect=.12)
    if rows_per_series is not None:
        frame = frame.groupby('series_id', sort=False).head(rows_per_series).copy()
    frame = frame.reset_index(drop=True)
    rng = np.random.default_rng(76543)
    frame['last_touch_team'] = rng.choice(possession.TOUCH_LEVELS, len(frame))
    frame['ball_vy_attack'] = rng.normal(0., 900., len(frame))
    frame['ball_in_opp_half'] = frame['ball_y'] > 0
    frame['possession_stratum'] = np.where(
        frame['last_touch_team'].eq('own') & frame['ball_vy_attack'].gt(0),
        'S_own', np.where(frame['last_touch_team'].eq('opponent'), 'S_opp', 'S_other'))
    frame['population'] = np.where(np.arange(len(frame)) % 2, 'late_trailing', 'tied')
    # The original encoder excludes validation-only levels and records their
    # player count. This checks that the memory rewrite preserves that behavior.
    validation_only = frame['split'].eq('val') & (np.arange(len(frame)) % 17 == 0)
    frame.loc[validation_only, 'last_man_id'] = 'validation-only-player'
    frame.loc[validation_only, 'region'] = 'validation-only-region'
    assigned, _ = dr.freeze_initiation(frame, delta=500., control='third', include_early=False)
    return assigned.loc[assigned['treatment'].notna()].reset_index(drop=True)


class PossessionLowmemEquivalence(unittest.TestCase):
    def assert_nested_equivalent(self, original, lowmem, path='result'):
        if isinstance(original, dict):
            self.assertIsInstance(lowmem, dict, path)
            self.assertEqual(set(original), set(lowmem), path)
            for key in original:
                self.assert_nested_equivalent(original[key], lowmem[key], f'{path}.{key}')
        elif isinstance(original, np.ndarray):
            self.assertEqual(original.shape, np.asarray(lowmem).shape, path)
            np.testing.assert_allclose(original, lowmem, rtol=RTOL, atol=ATOL,
                                       equal_nan=True, err_msg=path)
        elif isinstance(original, (list, tuple)):
            self.assertEqual(len(original), len(lowmem), path)
            for index, (left, right) in enumerate(zip(original, lowmem)):
                self.assert_nested_equivalent(left, right, f'{path}[{index}]')
        elif isinstance(original, (bool, np.bool_, numbers.Integral)) or original is None:
            # Gate outcomes, counts, membership and missingness cannot drift.
            self.assertEqual(original, lowmem, path)
        elif isinstance(original, numbers.Real):
            np.testing.assert_allclose(original, lowmem, rtol=RTOL, atol=ATOL,
                                       equal_nan=True, err_msg=path)
        else:
            self.assertEqual(original, lowmem, path)

    def compare_pipeline(self, frame, original_workers):
        original = possession.nuisance_predictions(frame, workers=original_workers, lowmem=False)
        reduced = possession.nuisance_predictions(frame, workers=original_workers, lowmem=True)
        old_predictions, old_features, old_manifest = original
        new_predictions, new_features, new_manifest = reduced
        self.assertEqual(old_features.dtype, new_features.dtype)
        self.assertEqual(old_features.shape, new_features.shape)
        self.assertEqual(old_features.tobytes(order='C'), new_features.tobytes(order='C'),
                         'All feature values, including signed zeros, must match bitwise')
        np.testing.assert_array_equal(np.isnan(old_predictions), np.isnan(new_predictions))
        np.testing.assert_allclose(old_predictions, new_predictions, rtol=RTOL, atol=ATOL,
                                   equal_nan=True)
        self.assertEqual(old_manifest, new_manifest)
        self.assertGreater(old_manifest['unknown_validation_last_man_id_rows'], 0)
        self.assertEqual(old_manifest['folds'], 3)
        self.assertEqual(old_manifest['max_iter'], 80)
        names = old_manifest['feature_names']
        old_estimates, old_urgency = possession.analyze(frame, old_predictions, old_features, names)
        new_estimates, new_urgency = possession.analyze(frame, new_predictions, new_features, names)
        self.assert_nested_equivalent(old_estimates, new_estimates, 'estimates')
        self.assert_nested_equivalent(old_urgency, new_urgency, 'urgency')
        self.assertEqual(old_urgency['bootstrap_repeats'], 2000)
        old_rules = possession.evaluate_rules(old_estimates, old_urgency)
        new_rules = possession.evaluate_rules(new_estimates, new_urgency)
        self.assert_nested_equivalent(old_rules, new_rules, 'rules')
        self.assertEqual(set(old_rules), {'R1', 'R2', 'R3', 'R4', 'R5'})

    def test_serial_features_predictions_estimates_and_rules(self):
        self.compare_pipeline(possession_fixture(), original_workers=1)

    def test_four_fit_workers_against_serial_lowmem(self):
        self.compare_pipeline(possession_fixture(rows_per_series=12), original_workers=4)

    def test_historical_eight_inner_threads_against_serial_lowmem(self):
        # Original --workers=32 schedules four fit processes, eight threads each.
        # This exercises that scheduler change, without claiming equivalence to
        # an unavailable historical medium artifact or dependency environment.
        self.compare_pipeline(possession_fixture(rows_per_series=12), original_workers=32)


if __name__ == '__main__':
    unittest.main()
