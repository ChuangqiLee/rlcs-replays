"""CPU-only synthetic checks for matched retrieval and failure diagnostics."""
import json
import unittest

import numpy as np
import pandas as pd

from ai_experiments.diagnostics import embedding_diagnostics, optimizer_diagnostics, parameter_snapshot
from ai_experiments.evaluation import evaluate_methods, train_standardize
from tactics_code.style_retrieval import evaluate_retrieval, metric_scores


def fixture(seed=9):
    rng = np.random.default_rng(seed)
    ids = [f"p{i}" for i in range(6)]
    rows, metadata = [], []
    for split, season, rosters in (("train", "rlcs-2024", [[0, 1, 2], [3, 4, 5]]),
                                   ("val", "rlcs-2025", [[0, 3, 4], [1, 2, 5]])):
        for game in range(20):
            replay, series = f"{split}-replay-{game}", f"{split}-series-{game // 5}"
            for team in rosters:
                roster = ":".join(ids[i] for i in team)
                metadata.append(dict(split=split, season=season, replay_id=replay,
                                     series_id=series, roster_id=roster, region="EU",
                                     player_ids=json.dumps([ids[i] for i in team])))
                for identity in team:
                    rows.append(dict(split=split, season=season, replay_id=replay,
                                     series_id=series, roster_id=roster, identity_id=ids[identity],
                                     f_0=rng.normal(), f_1=rng.normal(), f_2=rng.normal()))
    return pd.DataFrame(rows), metadata


class EvaluationTests(unittest.TestCase):
    def test_identical_methods_match_original_and_have_zero_paired_difference(self):
        games, metadata = fixture()
        columns = ["f_0", "f_1", "f_2"]
        x = games[columns].to_numpy()
        methods = {name: dict(values=x.copy(), metric="euclidean", standardize=True)
                   for name in ("handcrafted", "identical")}
        report = evaluate_methods(games, metadata, methods, bootstrap=79, seed=42)
        old = evaluate_retrieval(games[games.split == "train"], games[games.split == "val"],
                                 columns, metadata, permutations=0, bootstrap=79, seed=42)
        self.assertEqual(report["population"]["eligible_ids"], old["eligible_ids"])
        for analysis in ("primary", "team_context_control"):
            for metric in ("top1", "top5", "mrr"):
                actual = report[analysis]["methods"]["handcrafted"]["metrics"][metric]
                np.testing.assert_allclose(actual["estimate"], old[analysis]["metrics"][metric]["estimate"])
                np.testing.assert_allclose(actual["ci95"], old[analysis]["metrics"][metric]["ci95"])
                paired = report[analysis]["methods"]["identical"]["paired_difference_vs_baseline"][metric]
                self.assertEqual(paired, {"estimate": 0., "ci95": [0., 0.]})
        json.dumps(report, allow_nan=False)

    def test_fractional_ties_are_not_broken_by_candidate_order(self):
        scores = metric_scores(np.ones((2, 6)), np.array([0, 5]), np.ones((2, 6), bool))
        np.testing.assert_allclose(scores[:, 0], 1 / 6)
        np.testing.assert_allclose(scores[:, 1], 5 / 6)
        np.testing.assert_allclose(scores[:, 2], np.sum(1 / np.arange(1, 7)) / 6)

    def test_scaling_does_not_use_validation(self):
        x = np.array([[1., np.nan], [3., np.nan], [1e9, 100.]])
        transformed, state = train_standardize(x, [True, True, False])
        self.assertEqual(state["mean"], [2., 0.])
        self.assertEqual(state["scale"], [1., 1.])
        self.assertEqual(state["all_missing_feature_indices"], [1])
        np.testing.assert_array_equal(transformed[:2], [[-1., 0.], [1., 0.]])

    def test_fusion_scale_is_train_only_and_population_is_shared(self):
        games, metadata = fixture()
        x = games[["f_0", "f_1", "f_2"]].to_numpy().copy()
        methods = {"handcrafted": dict(values=x, metric="euclidean", standardize=True),
                   "learned": dict(values=x + 5., metric="cosine", center=True),
                   "fusion": dict(components=["handcrafted", "learned"])}
        before = evaluate_methods(games, metadata, methods, bootstrap=9)
        x[games.split.eq("val")] += 1000.
        after = evaluate_methods(games, metadata, methods, bootstrap=9)
        self.assertEqual(before["methods"]["handcrafted"]["train_distance_scale"],
                         after["methods"]["handcrafted"]["train_distance_scale"])
        self.assertEqual(before["population"], after["population"])
        for name in methods:
            self.assertEqual(len(before["primary"]["methods"][name]["per_query"]), 24)

    def test_individual_season_gate_cannot_pool_ten_plus_ten(self):
        games, metadata = fixture()
        train = games.split.eq("train")
        rows = np.flatnonzero(train)
        games.loc[rows[:60], "season"] = "rlcs-21-22"
        games.loc[rows[60:], "season"] = "rlcs-22-23"
        result = evaluate_methods(games, metadata, {"handcrafted": games[["f_0"]].to_numpy()})
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["population"]["n_gallery"], 0)

    def test_forbidden_and_duplicate_rows_refused(self):
        games, metadata = fixture()
        bad = games.copy()
        bad.loc[0, "season"] = "rlcs-2026"
        with self.assertRaisesRegex(ValueError, "Forbidden"):
            evaluate_methods(bad, metadata, {"handcrafted": bad[["f_0"]].to_numpy()})
        duplicate = pd.concat([games, games.iloc[:1]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate_methods(duplicate, metadata, {"handcrafted": duplicate[["f_0"]].to_numpy()})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            evaluate_methods(games, metadata, {"handcrafted": np.ones((3, 2))})

    def test_cross_split_replay_or_series_refused(self):
        games, metadata = fixture()
        games.loc[games.split.eq("val"), "series_id"] = games.iloc[0].series_id
        with self.assertRaisesRegex(ValueError, "series"):
            evaluate_methods(games, metadata, {"handcrafted": games[["f_0"]].to_numpy()})

    def test_constant_embeddings_diagnostic_reports_rank_zero(self):
        report = embedding_diagnostics(np.ones((8, 4)), np.repeat([0, 1], 4))
        self.assertEqual(report["effective_rank_centered_covariance"], 0.)
        self.assertEqual(report["mean_feature_variance"], 0.)
        self.assertAlmostEqual(report["same_minus_different_cosine"], 0.)
        self.assertAlmostEqual(report["uniform_self_excluded_supcon_loss"], np.log(7))
        json.dumps(report, allow_nan=False)

    def test_embeddings_diagnostic_detects_planted_identity_signal(self):
        x = np.repeat(np.eye(3), 4, axis=0)
        report = embedding_diagnostics(x, np.repeat(np.arange(3), 4))
        self.assertGreater(report["same_minus_different_cosine"], .99)
        self.assertAlmostEqual(report["effective_rank_centered_covariance"], 2.)

    def test_optimizer_diagnostic_distinguishes_updates_from_nonfinite_gradients(self):
        import torch
        model = torch.nn.Linear(2, 1)
        before = parameter_snapshot(model)
        opt = torch.optim.SGD(model.parameters(), lr=.1)
        model(torch.ones(3, 2)).sum().backward()
        opt.step()
        report = optimizer_diagnostics(model, before)
        self.assertGreater(report["gradient_l2_norm"], 0.)
        self.assertGreater(report["parameter_delta_l2_norm"], 0.)
        self.assertEqual(report["nonfinite_gradient_parameters"], [])
        model.weight.grad.fill_(float("nan"))
        report = optimizer_diagnostics(model, before)
        self.assertIn("weight", report["nonfinite_gradient_parameters"])
        self.assertIsNone(report["gradient_l2_norm"])
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
