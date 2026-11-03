"""CPU checks for goal-risk labels, symmetrization, metrics and calibration."""
import unittest

import numpy as np
import torch

from ai_experiments.risk_data import goal_events, labels_for, HORIZONS
from ai_experiments.riskrun import (CONTEXT_DIM, RiskNet, apply_scaling, auroc, context_vector, evaluate,
                                    masked_ce, softmax, symmetrize, vector_scaling)


class LabelTests(unittest.TestCase):
    def test_competing_first_goal(self):
        t = np.array([0., 5., 12., 30.])
        lab, dt_own, dt_opp = labels_for(t, np.array([8.]), np.array([25.]), 40., False)
        np.testing.assert_array_equal(lab['y10'], [1, 1, 0, 0])
        np.testing.assert_array_equal(lab['y20'], [1, 1, 2, -1])
        np.testing.assert_array_equal(dt_own, [8., 3., np.inf, np.inf])
        np.testing.assert_array_equal(dt_opp, [25., 20., 13., np.inf])

    def test_certified_terminal_is_absorbing(self):
        lab, _, _ = labels_for(np.array([35.]), np.array([]), np.array([]), 40., True)
        self.assertEqual(lab['y10'][0], 0)
        self.assertEqual(lab['y20'][0], 0)
        lab, _, _ = labels_for(np.array([35.]), np.array([]), np.array([]), 40., False)
        self.assertEqual(lab['y20'][0], -1)

    def test_goal_events_from_score_transitions(self):
        arrays = dict(score_diff=np.array([0, 0, 1, 1, 0, np.nan, 0, -1.]), time=np.arange(8.))
        times, delta = goal_events(arrays)
        np.testing.assert_array_equal(times, [2., 4., 7.])
        np.testing.assert_array_equal(np.sign(delta), [1, -1, -1])


class ModelTests(unittest.TestCase):
    def test_history_and_snapshot_shapes(self):
        cfg = dict(width=16, heads=2, spatial_layers=1, temporal_layers=1, dropout=.0)
        ctx = torch.as_tensor(context_vector(np.array([-1., 0.]), np.array([30., 200.]), np.array([0., 1.])))
        self.assertEqual(ctx.shape, (2, CONTEXT_DIM))
        for history in (60, 1):
            model = RiskNet(cfg, history)
            x = torch.randn(2, history, 7, 16)
            x[..., 15] = 1.
            logits = model(x, ctx)
            self.assertEqual(logits.shape, (2, len(HORIZONS), 3))
            loss, parts = masked_ce(logits, torch.tensor([[1, -1], [0, 2]]))
            self.assertTrue(torch.isfinite(loss))
            self.assertIn('ce10', parts)


class EvaluationTests(unittest.TestCase):
    def test_symmetrize_swaps_for_against(self):
        prob = np.array([[[.5, .3, .2]], [[.2, .1, .7]], [[.6, .2, .2]]])  # [N,1,3]
        keys = np.array(['r:1', 'r:1', 'r:2'])
        team = np.array([0, 1, 0])
        sym, rep = symmetrize(prob, keys, team)
        np.testing.assert_allclose(sym[0, 0], [.35, .5, .15])
        self.assertEqual(set(rep.tolist()), {0, 2})

    def test_auroc_matches_rank_definition(self):
        score = np.array([.1, .4, .35, .8])
        label = np.array([0, 0, 1, 1])
        self.assertAlmostEqual(auroc(score, label), .75)

    def test_evaluate_and_scaling(self):
        rng = np.random.default_rng(0)
        n = 400
        y = rng.integers(0, 3, (n, 2))
        series = np.repeat(np.arange(20), n // 20).astype(str)
        logits = rng.normal(0, 1, (n, 2, 3)) + 2 * np.eye(3)[y]
        good = softmax(logits)
        bad = softmax(rng.normal(0, 1, (n, 2, 3)))
        report = evaluate({'good': good, 'bad': bad}, y, series, bootstrap=50)
        self.assertLess(report['H10']['point']['good']['logloss'], report['H10']['point']['bad']['logloss'])
        self.assertLess(report['H10']['paired']['good-bad']['logloss']['ci95'][1], 0)
        params = vector_scaling(logits * 3, y)  # overconfident logits get tempered
        scaled = apply_scaling(logits * 3, params)
        before = -np.log(softmax(logits * 3)[np.arange(n), 0, y[:, 0]]).mean()
        after = -np.log(softmax(scaled)[np.arange(n), 0, y[:, 0]]).mean()
        self.assertLess(after, before)


if __name__ == '__main__':
    unittest.main()
