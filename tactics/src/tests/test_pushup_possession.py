"""Contracts for the preregistered possession sensitivity; no replay data read.

Run with PYTHONPATH=src python -m unittest tests.test_pushup_possession -v.
The confounding fixture has exact arm balance within possession levels, and
identical potential outcomes under either arm by construction.
"""
import copy
import unittest

import numpy as np
import pandas as pd

from tactics_code import pushup_dr as dr
from tactics_code import pushup_possession as possession


def compact_fixture():
    t = np.arange(301, dtype=float) / 10
    players = np.zeros((len(t), 6, 8), dtype=np.float32)
    players[:, :, 0] = t[:, None] * 10 + np.arange(6)[None, :] * 100
    players[:, :, 1] = [-3500, -2000, -1000, 1000, 2000, 3500]
    players[:, :, 3] = 10
    players[:, :, 6] = 50
    ball = np.zeros((len(t), 6), dtype=np.float32)
    ball[:, 1], ball[:, 2], ball[:, 4] = 100, 100, 200
    a = dict(time=t, players=players, ball=ball, frame=np.arange(len(t)) * 3,
             touch=np.full(len(t), -1, dtype=np.int8),
             live=np.ones(len(t), dtype=bool), segment=np.zeros(len(t), dtype=int),
             remaining=np.full(len(t), 40.), score_diff=np.zeros(len(t)),
             overtime=np.zeros(len(t)))
    a['touch'][80] = 0
    meta = dict(replay_id='synthetic', series_id='synthetic-series',
                season='rlcs-2024', split='train', focal_team=0,
                region='synthetic', roster_id='own', opponent_roster_id='opp',
                player_ids=[str(j) for j in range(6)])
    replay = dict(replay_id='synthetic', validated=True,
                  observed_start_time=0., observed_end_time=30.,
                  terminal_verified=False, terminal_time=None,
                  gap_start_times='[]', gap_end_times='[]')
    goals = pd.DataFrame({'time': pd.Series(dtype=float),
                          'scoring_team': pd.Series(dtype=int),
                          'frame': pd.Series(dtype=int)})
    return a, meta, replay, goals


def all_anchor_features(a, meta, replay, goals):
    frame, _ = dr.anchors_for_replay(meta, a, goals, replay, 42,
                                     design='initiation')
    indices = np.searchsorted(a['time'], frame['anchor_time'].to_numpy())
    extra = possession.possession_features(a, indices)
    for name in extra.columns:
        frame[name] = extra[name].to_numpy()
    return frame


def planted_confounding():
    # Per series: possession P1 drives treatment (.8 vs .2) and scoring
    # (.7 vs .3). Within either P1 level, outcomes are exactly independent
    # of treatment. Every row has the same outcome under A=0 and A=1.
    cells = [('own', 0, 7, 3), ('own', 1, 28, 12),
             ('opponent', 0, 12, 28), ('opponent', 1, 3, 7)]
    rows = []
    for series in range(180):
        for touch, arm, scores, concedes in cells:
            for y in [1] * scores + [2] * concedes:
                rows.append((f'series-{series:03d}', 'train' if series < 120 else 'val',
                             touch, arm, y))
    df = pd.DataFrame(rows, columns=['series_id', 'split', 'last_touch_team',
                                     'treatment', 'y10'])
    for name in dr.NUMERIC_FEATURES:
        df[name] = 0.
    df['remaining'], df['score_diff'] = 30., -1.
    df['ball_y'], df['ball_vy'] = 100., 200.
    df['last_man_y_own'], df['last_man_behind_ball'] = 1000., 4000.
    df['region'], df['last_man_id'] = 'synthetic', 'defender'
    df['ball_vy_attack'], df['ball_in_opp_half'] = 200., True
    df['possession_stratum'] = np.where(df['last_touch_team'] == 'own', 'S_own', 'S_opp')
    df['population'] = 'late_trailing'
    df['goal_id10'] = [f'goal-{i}' for i in range(len(df))]
    df['followup_extra_seconds'] = 0.
    return df


class PossessionFeaturesTest(unittest.TestCase):
    def test_velocity_tertiles_are_frozen_without_validation_values(self):
        df = pd.DataFrame({'split': ['train'] * 6 + ['val'] * 2,
                           'series_id': ['a'] * 3 + ['b'] * 3 + ['v'] * 2,
                           'ball_vy_attack': [-900., -300., 0., 100., 500., 900., -1e6, 1e6]})
        before = possession.freeze_velocity_tertiles(df)
        df.loc[df['split'] == 'val', 'ball_vy_attack'] = [1e20, 1e20]
        after = possession.freeze_velocity_tertiles(df)
        self.assertEqual(before['fit_split'], 'train')
        self.assertEqual(before['rows'], 6)
        self.assertEqual(before['series'], 2)
        np.testing.assert_array_equal(before['cutpoints'], after['cutpoints'])
        self.assertTrue(np.all(np.abs(before['cutpoints']) <= 900))

    def test_future_touches_and_all_future_state_do_not_change_features(self):
        a, meta, replay, goals = compact_fixture()
        before = all_anchor_features(a, meta, replay, goals)
        t = before.loc[before['anchor_time'] >= 10, 'anchor_time'].iloc[0]
        changed = {key: value.copy() for key, value in a.items()}
        future = a['time'] > t
        changed['touch'][future] = 5  # every future touch flips to opponent
        changed['ball'][future] = -9999
        changed['players'][future] = 9999
        changed['remaining'][future] = 10000
        changed['score_diff'][future] = -1
        changed['overtime'][future] = 1
        changed['live'][future] = False
        changed['segment'][future] = -1
        after = all_anchor_features(changed, meta, replay, goals)
        row0 = before[before['anchor_time'] == t].reset_index(drop=True)
        row1 = after[after['anchor_time'] == t].reset_index(drop=True)
        self.assertEqual(len(row0), 1)
        self.assertEqual(len(row1), 1)
        x0, names0, _ = possession.feature_matrix(row0, np.array([True]))
        x1, names1, _ = possession.feature_matrix(row1, np.array([True]))
        self.assertEqual(names0, names1)
        np.testing.assert_array_equal(x0, x1)
        self.assertEqual(row0['last_touch_team'].iloc[0], 'own')
        self.assertEqual(row1['last_touch_team'].iloc[0], 'own')
        pd.testing.assert_frame_equal(
            possession.possession_features(a, np.flatnonzero(a['time'] <= t)),
            possession.possession_features(changed, np.flatnonzero(a['time'] <= t)))

    def test_touch_window_is_open_left_closed_right(self):
        a, _, _, _ = compact_fixture()
        a['touch'][:] = -1
        a['touch'][50] = 0
        a['touch'][101] = 5
        result = possession.possession_features(a, np.array([99, 100, 101]))
        self.assertEqual(result['last_touch_team'].tolist(), ['own', 'none', 'opponent'])
        self.assertEqual(result['possession_stratum'].tolist(), ['S_own', 'S_other', 'S_opp'])

    def test_compact_slots_and_attack_direction_in_both_perspectives(self):
        own, _, _, _ = compact_fixture()
        own['touch'][:] = -1
        own['touch'][100] = 2
        other = {key: value.copy() for key, value in own.items()}
        other['touch'][100] = 5
        other['ball'][:, [0, 1, 3, 4]] *= -1
        b = possession.possession_features(own, np.array([100])).iloc[0]
        o = possession.possession_features(other, np.array([100])).iloc[0]
        self.assertEqual((b['last_touch_team'], o['last_touch_team']), ('own', 'opponent'))
        self.assertEqual((b['ball_vy_attack'], o['ball_vy_attack']), (200., -200.))
        self.assertTrue(b['ball_in_opp_half'])
        self.assertFalse(o['ball_in_opp_half'])
        own['ball'][100, 1] = 0
        own['ball'][100, 4] = 0
        zero = possession.possession_features(own, np.array([100])).iloc[0]
        self.assertFalse(zero['ball_in_opp_half'])
        self.assertEqual(zero['possession_stratum'], 'S_other')


class PlantedConfoundingTest(unittest.TestCase):
    def test_possession_adjustment_recovers_planted_zero_effect(self):
        df = planted_confounding()
        self.assertEqual(len(df), 18000)
        rates = df.groupby(['last_touch_team', 'treatment'])['y10'].mean().unstack()
        np.testing.assert_array_equal(rates[0], rates[1])
        pred, x, nuisance = possession.nuisance_predictions(df, workers=1)
        val = df['split'].eq('val').to_numpy()
        adjusted = possession.estimate_contrast(
            df.loc[val].reset_index(drop=True), pred[val], x[val], nuisance['feature_names'])
        # Remove the only informative confounder from an otherwise identical
        # train-frozen DR fit, so this is an unconditioned estimator comparison.
        blind = df.copy()
        blind['last_touch_team'], blind['possession_stratum'] = 'none', 'S_other'
        naive_pred, naive_x, naive_nuisance = possession.nuisance_predictions(blind, workers=1)
        unconditioned = possession.estimate_contrast(
            blind.loc[val].reset_index(drop=True), naive_pred[val], naive_x[val],
            naive_nuisance['feature_names'])
        corrected = float(adjusted['adjusted']['difference_net_gd']['estimate'])
        uncorrected = float(unconditioned['adjusted']['difference_net_gd']['estimate'])
        self.assertLess(abs(corrected), .02)
        self.assertGreater(abs(uncorrected), .40)
        self.assertTrue(adjusted['estimable'])
        self.assertEqual(nuisance['folds'], 3)
        self.assertEqual(nuisance['validation_rows_used_in_fit'], 0)
        print(f'planted_confounded_zero_effect: full_model={corrected:.8f}, '
              f'unconditioned={uncorrected:.8f}, true_effect=0')


def rule_fixture():
    result = dict(adjusted={'difference_net_gd': {'estimate': .044, 'ci95': [-.01, .08]},
                            'difference_against': {'estimate': 0., 'ci95': [-.01, .01]}},
                  estimable=True, minimum_arm_series_ess=20., status='computed_association_causal_gate_failed',
                  causal_identification=False, trim_fraction=.1,
                  balance={'max_abs_smd_after': .2,
                           'arms': {'0': {'series_weight_ess': 20., 'anchor_weight_ess': 100.},
                                    '1': {'series_weight_ess': 21., 'anchor_weight_ess': 100.}}})
    return {name: copy.deepcopy(result) for name in ('full_model', 'S_own', 'S_opp', 'tied_full_model')}


class PreregisteredRulesTest(unittest.TestCase):
    def test_r1_inclusive_magnitude_and_ci_boundaries(self):
        estimates = rule_fixture()
        urgency = {'estimate': 0., 'ci95': [-.01, .01]}
        for point, interval in ((-.044, [-.1, 0.]), (.044, [0., .1]), (0., [0., 0.])):
            with self.subTest(point=point, ci=interval):
                estimates['full_model']['adjusted']['difference_net_gd'] = {
                    'estimate': point, 'ci95': interval}
                self.assertTrue(possession.evaluate_rules(estimates, urgency)['R1']['pass'])
        estimates['full_model']['adjusted']['difference_net_gd'] = {
            'estimate': .044000001, 'ci95': [-.1, .1]}
        self.assertFalse(possession.evaluate_rules(estimates, urgency)['R1']['pass'])
        estimates['full_model']['adjusted']['difference_net_gd'] = {
            'estimate': .01, 'ci95': [.001, .02]}
        self.assertFalse(possession.evaluate_rules(estimates, urgency)['R1']['pass'])
        # Missing support is represented by no interval, not a significant result.
        estimates['full_model']['adjusted']['difference_net_gd']['ci95'] = None
        self.assertFalse(possession.evaluate_rules(estimates, urgency)['R1']['pass'])

    def test_r2_negative_interval_and_r3_zero_concede_boundary(self):
        estimates = rule_fixture()
        urgency = {'estimate': 0., 'ci95': [-.01, .01]}
        estimates['S_opp']['adjusted']['difference_net_gd'] = {'estimate': -.01, 'ci95': [-.02, 0.]}
        rules = possession.evaluate_rules(estimates, urgency)
        self.assertFalse(rules['R2']['pass'])
        self.assertTrue(rules['R3']['pass'])
        estimates['S_opp']['adjusted']['difference_net_gd']['ci95'][1] = -.001
        estimates['S_opp']['adjusted']['difference_against']['estimate'] = -1e-9
        rules = possession.evaluate_rules(estimates, urgency)
        self.assertTrue(rules['R2']['pass'])
        self.assertFalse(rules['R3']['pass'])
        estimates['S_opp']['estimable'] = False
        estimates['S_opp']['adjusted']['difference_against']['estimate'] = .1
        rules = possession.evaluate_rules(estimates, urgency)
        self.assertFalse(rules['R2']['pass'])
        self.assertFalse(rules['R3']['pass'])
        self.assertFalse(rules['R4']['pass'])

    def test_r5_support_and_smoke_do_not_produce_claims(self):
        estimates = rule_fixture()
        urgency = {'estimate': .1, 'ci95': [0., .2]}
        self.assertFalse(possession.evaluate_rules(estimates, urgency)['R5']['pass'])
        urgency['ci95'] = [.01, .2]
        self.assertTrue(possession.evaluate_rules(estimates, urgency)['R5']['pass'])
        estimates['tied_full_model']['estimable'] = False
        self.assertFalse(possession.evaluate_rules(estimates, urgency)['R5']['pass'])
        estimates['tied_full_model']['estimable'] = True
        estimates['S_opp']['adjusted']['difference_net_gd'] = {'estimate': -.1, 'ci95': [-.2, -.01]}
        rules = possession.evaluate_rules(estimates, urgency, smoke=True)
        for name in ('R1', 'R2', 'R3', 'R5'):
            self.assertFalse(rules[name]['pass'])
        self.assertEqual(set(rules), {'R1', 'R2', 'R3', 'R4', 'R5'})
        self.assertTrue(all('inputs' in rule for rule in rules.values()))

    def test_r4_series_ess_boundary_without_relaxing_original_causal_gate(self):
        for count, estimable in ((19, False), (20, True)):
            with self.subTest(series=count):
                df = pd.DataFrame({'series_id': np.repeat([f's{i}' for i in range(count)], 2),
                                   'treatment': np.tile([0, 1], count),
                                   'y10': np.tile([2, 1], count),
                                   'goal_id10': [f'g{i}' for i in range(2 * count)]})
                pred = np.full((len(df), 25), np.nan)
                pred[:, 0] = .5
                pred[:, 7:13] = [0., .5, .5, 0., .5, .5]
                result = possession.estimate_contrast(df, pred, np.zeros((len(df), 1)), ['constant'])
                self.assertEqual(result['minimum_arm_series_ess'], count)
                self.assertEqual(result['estimable'], estimable)
                self.assertFalse(result['causal_identification'])
                if not estimable:
                    self.assertEqual(result['status'], 'not_estimable')

    def test_paired_urgency_keeps_series_covariance_and_union_target(self):
        # A fixed within-series difference has no bootstrap variation despite
        # large between-series heterogeneity: independent draws would fail this.
        late = pd.Series(np.linspace(-.8, .8, 100), index=[f's{i}' for i in range(100)])
        tied = late - .2
        shared = possession.paired_urgency(late, tied)
        self.assertAlmostEqual(shared['estimate'], .2)
        np.testing.assert_allclose(shared['ci95'], [.2, .2], atol=1e-12)
        self.assertEqual(shared['shared_series'], 100)
        self.assertEqual(shared['invalid_bootstrap_replicates'], 0)
        # Dropping non-shared series would change the answer to .5, whereas
        # marginal equal-series means over the union give 2 - (-.5) = 2.5.
        late = pd.Series({'shared': 1., 'late-only': 3.})
        tied = pd.Series({'shared': .5, 'tied-only': -1.5})
        union = possession.paired_urgency(late, tied)
        self.assertAlmostEqual(union['estimate'], 2.5)
        self.assertEqual(union['union_series'], 3)
        self.assertEqual(union['shared_series'], 1)
        self.assertGreater(union['invalid_bootstrap_replicates'], 0)
        self.assertIsNone(union['ci95'])


if __name__ == '__main__':
    unittest.main()
