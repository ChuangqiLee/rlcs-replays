"""Local synthetic checks; no native replay data or network required."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tactics_code import pressure
from tactics_code import pressure_variants as pv
from tactics_code.stats import bootstrap_ols, cluster_ols

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "artifacts"


def fixture_records(n_series=24, repeats=128):
    """Both views share the same series, replay clock and global geometry."""
    rng = np.random.default_rng(pv.SEED)
    records, chunks, expected = [], [], []
    count = 0
    for series in range(n_series):
        offset, leading_noise, trailing_noise = rng.normal(0, [30, 12, 12])
        lead = -180 + leading_noise
        interaction = 620 + trailing_noise
        expected.append((lead, lead + interaction, interaction))
        for replay in range(2):
            score = np.repeat([1., -1., 1., -1., 0., 0.], 4 * repeats)
            remaining = np.tile(np.repeat([135., 110., 85., 65.], repeats), 6)
            remaining[8 * repeats:20 * repeats] = np.tile(np.repeat([55., 40., 25., 10.], repeats), 3)
            remaining[20 * repeats:] = 0
            overtime = np.repeat([0., 0., 0., 0., 0., 1.], 4 * repeats)
            n = len(score)
            ball = np.zeros((n, 6))
            ball[:, 2] = 100
            ball[:, 3] = 500
            ball[:, 1] = np.tile(np.repeat([-2200., -800., 800., 2200.], repeats), 6)
            players = np.zeros((n, 6, 8))
            for team in (0, 1):
                own_score = score if team == 0 else -score
                late = (remaining <= pv.LATE_SECONDS) & (overtime == 0)
                depth = (2400 + offset + 80 * (own_score < 0) + lead * late
                         + interaction * (late & (own_score < 0)) + 110 * overtime)
                local_y = depth[:, None] - pv.GOAL_OFFSET + np.array([0., 700., 1400.])
                sign = 1 if team == 0 else -1
                players[:, team * 3:(team + 1) * 3, 1] = sign * local_y
            players[:, :, 0] = np.array([-600, 0, 600, 600, 0, -600])
            players[:, :, 2] = 17
            players[:, :, 6] = 50
            for team in (0, 1):
                indices = [0, 1, 2, 3, 4, 5] if team == 0 else [3, 4, 5, 0, 1, 2]
                view_players = players[:, indices, :].copy()
                view_ball = ball.copy()
                if team == 1:
                    view_players[:, :, [0, 1, 3, 4]] *= -1
                    view_ball[:, [0, 1, 3, 4]] *= -1
                arrays = {"players": view_players, "ball": view_ball,
                          "roles": np.tile([2, 1, 0], (n, 1)), "live": np.ones(n, bool),
                          "score_diff": score.copy() if team == 0 else -score,
                          "remaining": remaining.copy(), "overtime": overtime.copy()}
                meta = dict(replay_id=f"synthetic-{series}-{replay}", series_id=f"series-{series}",
                            season=pv.VAL_SEASON, split="val", roster_id=f"roster-{team}",
                            team_id=f"team-{team}", event="fixture", region="EU", focal_team=team,
                            state_source="synthetic_fixture", start=count, stop=count + n)
                records.append(meta)
                chunks.append(arrays)
                count += n
    return records, chunks, np.mean(expected, axis=0)


def write_fixture(root, n_series=24, repeats=128):
    root = Path(root)
    directory = root / pv.VAL_SEASON
    directory.mkdir(parents=True, exist_ok=True)
    records, chunks, expected = fixture_records(n_series, repeats)
    np.savez_compressed(directory / "compact-0000.npz",
                        **{key: np.concatenate([chunk[key] for chunk in chunks]) for key in chunks[0]})
    pd.DataFrame(records).to_parquet(directory / "compact-0000.parquet", index=False)
    (root / "extraction.json").write_text(json.dumps({"synthetic_fixture": True,
        "expected_regulation": dict(zip(("leading", "trailing", "interaction"), expected)),
        "perspectives": len(records), "frames": sum(len(c["live"]) for c in chunks)}, indent=2))
    return root


class PressureVariantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="p6-unit-", dir=OUTPUT_ROOT)
        cls.root = Path(cls.temporary.name)
        cls.metas, cls.arrays, cls.expected = fixture_records(n_series=12, repeats=1)
        observations = pd.DataFrame([row for meta, arrays in zip(cls.metas, cls.arrays)
                                     for row in pv.summarize_variants(meta, arrays)])
        cls.summary = pv.aggregate_variants(observations)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_read_only_geometry_masks_and_both_views(self):
        for team in (0, 1):
            arrays = {key: value.copy() for key, value in self.arrays[team].items()}
            arrays["players"][1, 1, 7] = 1
            arrays["players"][2, 2, 0] = np.nan
            before = {key: value.copy() for key, value in arrays.items()}
            for a in arrays.values():
                a.flags.writeable = False
            result = pv.definition_arrays(arrays)
            self.assertTrue(np.isnan(result["centroid_y_own"][[1, 2]]).all())
            valid = pressure.last_man_arrays(arrays)["last_man_valid"]
            np.testing.assert_allclose(result["mean_three_player_depth"][valid] - result["centroid_y_own"][valid], pv.GOAL_OFFSET)
            rows = pv.summarize_variants(self.metas[team], arrays)
            self.assertEqual(sum(row["centroid_y_own_n"] for row in rows), int(valid.sum()))
            for key in arrays:
                np.testing.assert_array_equal(arrays[key], before[key])

    def test_summary_preserves_pressure_and_alias(self):
        original = pd.DataFrame([row for m, a in zip(self.metas, self.arrays)
                                 for row in pressure.summarize_replay(m, a)])
        expected = pressure.series_context_summary(original)
        pd.testing.assert_frame_equal(self.summary[expected.columns], expected)
        np.testing.assert_allclose(self.summary.mean_three_player_depth - self.summary.centroid_y_own,
                                   pv.GOAL_OFFSET)
        for name in pv.EXTRA_RESPONSES:
            np.testing.assert_array_equal(self.summary[name + "_n"], self.summary.last_man_y_own_n)

    def test_linear_contrast_preserves_joint_covariance(self):
        rng = np.random.default_rng(pv.SEED)
        x = np.column_stack([np.ones(120), rng.normal(size=(120, 3))])
        groups = np.repeat(np.arange(12), 10)
        y = x @ np.array([4., -2., 3., 6.]) + rng.normal(size=120)
        weights = np.array([0., 1., 0., 1.])
        transformed, index = pv.reparameterize(x, weights)
        fit = cluster_ols(transformed, y, groups)
        # Independent direct sandwich calculation verifies the cross-term.
        bread = np.linalg.inv(x.T @ x)
        beta = bread @ x.T @ y
        scores = np.stack([x[groups == g].T @ (y - x @ beta)[groups == g] for g in np.unique(groups)])
        covariance = bread @ scores.T @ scores @ bread * 12 / 11 * 119 / 116
        np.testing.assert_allclose(fit["beta"][index], weights @ beta)
        np.testing.assert_allclose(fit["se"][index] ** 2, weights @ covariance @ weights)

    def test_regulation_exact_pressure_estimator_and_arms(self):
        models = pv.regulation_contrasts(self.summary, "last_man_y_own")
        pressure_fit = pressure.fit_pressure(self.summary, n_bootstrap=pv.N_BOOTSTRAP,
                                              seed=pv.SEED, regression="ols")
        original = pressure_fit["corrected_models"]["last_man_y_own"]
        for key in ("estimate", "se", "p_value", "n_series", "n_rows", "series_bootstrap"):
            self.assertEqual(models["interaction"][key], original[key])
        for kind, expected in zip(("leading", "trailing", "interaction"), self.expected):
            model = models[kind]
            self.assertEqual(model["status"], "fit")
            self.assertAlmostEqual(model["estimate"], expected, places=7)
            self.assertEqual(model["n_series"], self.summary.series_id.nunique())
        self.assertLess(models["leading"]["ci_high"], 0)
        self.assertGreater(models["trailing"]["ci_low"], 0)

    def test_whole_series_bootstrap_matches_explicit_resampling(self):
        rng = np.random.default_rng(pv.SEED)
        groups = np.repeat(np.arange(8), 8)
        x = np.column_stack([np.ones(len(groups)), np.tile([0., 1.], len(groups) // 2)])
        y = rng.normal(size=len(groups)) + 2 * x[:, 1] + groups
        actual = bootstrap_ols(x, y, groups, 1, pv.N_BOOTSTRAP, pv.SEED)
        rng = np.random.default_rng(pv.SEED)
        values = []
        for _ in range(pv.N_BOOTSTRAP):
            counts = rng.multinomial(8, np.full(8, 1 / 8))
            indices = np.concatenate([np.tile(np.flatnonzero(groups == g), count)
                                      for g, count in enumerate(counts)])
            values.append(np.linalg.lstsq(x[indices], y[indices], rcond=None)[0][1])
        np.testing.assert_allclose([actual["ci_low"], actual["ci_high"]], np.quantile(values, [.025, .975]))

    def test_ot_selection_unknowns_zero_second_and_direction(self):
        base = self.summary.copy()
        zero = base.loc[base.overtime.eq(0) & base.score_diff.eq(0)].copy()
        zero["remaining"] = 0.
        zero["last_man_y_own"] = zero.last_man_y_own + 100
        bogus = zero.copy()
        bogus["overtime"] = np.nan
        bogus["last_man_y_own"] = 1e9
        non_tied_ot = zero.assign(overtime=1., score_diff=1., last_man_y_own=1e9)
        frame = pd.concat([base, zero, bogus, non_tied_ot], ignore_index=True)
        result = pv.overtime_contrasts(frame)
        clean = pv.overtime_contrasts(pd.concat([base, zero], ignore_index=True))
        self.assertEqual(result, clean)
        ot_mean = frame.loc[frame.overtime.eq(1) & frame.score_diff.eq(0), "last_man_y_own"].mean()
        tied_mean = frame.loc[frame.overtime.eq(0) & frame.score_diff.eq(0), "last_man_y_own"].mean()
        model = result["ot_minus_tied"]
        self.assertAlmostEqual(model["estimate"], ot_mean - tied_mean, places=7)
        self.assertEqual(model["n_series"], self.summary.series_id.nunique())
        self.assertGreater(pv.overtime_contrasts(base)["ot_minus_tied"]["estimate"], model["estimate"])

    def test_outcome_specific_support_and_missing_states(self):
        frame = self.summary.copy()
        frame.loc[frame.late.eq(1) & frame.score_diff.eq(1), "centroid_y_own"] = np.nan
        models = pv.regulation_contrasts(frame, "centroid_y_own")
        self.assertEqual(models["interaction"]["status"], "not_estimable")
        result = pv.overtime_contrasts(frame.loc[frame.overtime.eq(0)])
        self.assertTrue(all(model["status"] == "not_estimable" for model in result.values()))
        small = frame.loc[frame.series_id.isin(["series-0", "series-1"])]
        self.assertEqual(pv.regulation_contrasts(small, "last_man_y_own")["leading"]["status"], "not_estimable")

    def test_empty_report_has_every_contrast(self):
        result = pv.analyze(pd.DataFrame())
        self.assertEqual(set(result["contrasts"]), set(pv.CONTRASTS))
        for model in result["contrasts"].values():
            self.assertEqual(model["status"], "not_estimable")
            self.assertIsNone(model["p_value"])
            self.assertIn("n_series", model)

    def test_malformed_contexts_are_not_cast_to_valid_codes(self):
        arrays = {key: value.copy() for key, value in self.arrays[0].items()}
        arrays["score_diff"][0] = .5
        arrays["overtime"][1] = .5
        rows = pv.summarize_variants(self.metas[0], arrays)
        self.assertTrue(any(pd.isna(row["score_diff"]) for row in rows))
        self.assertTrue(any(pd.isna(row["overtime"]) for row in rows))

    def test_direct_inference_rejects_non_validation_rows(self):
        invalid = self.summary.assign(season="rlcs-2024", split="train")
        with self.assertRaises(ValueError):
            pv.regulation_contrasts(invalid, "last_man_y_own")
        with self.assertRaises(ValueError):
            pv.overtime_contrasts(invalid)

    def test_rank_lost_bootstrap_cannot_trigger_finding(self):
        bad_bootstrap = {"ci_low": -2., "ci_high": -1., "requested_replicates": pv.N_BOOTSTRAP,
                         "successful_replicates": pv.N_BOOTSTRAP - 1}
        with patch.object(pv, "bootstrap_ols", return_value=bad_bootstrap):
            model = pv.regulation_contrasts(self.summary, "last_man_y_own")["leading"]
        self.assertEqual(model["status"], "bootstrap_incomplete")
        self.assertIsNone(pv.direction(model))

    def test_val_only_metadata_and_symlink_guards_before_array_read(self):
        root = write_fixture(self.root / "guard", n_series=3, repeats=1)
        meta_path = root / pv.VAL_SEASON / "compact-0000.parquet"
        original = pd.read_parquet(meta_path)
        for season, split in (("rlcs-2026", "test"), ("rlcs-2024", "train"), (pv.VAL_SEASON, "test")):
            original.assign(season=season, split=split).to_parquet(meta_path, index=False)
            with patch.object(np, "load", side_effect=AssertionError("Numeric arrays opened")):
                with self.assertRaises(ValueError):
                    pv.run(root, self.root / "guard-result.json", self.root / "guard-artifacts")
        original.to_parquet(meta_path, index=False)
        shard = meta_path.with_suffix(".npz")
        shard.unlink()
        shard.symlink_to(self.root / "rlcs-2026" / "forbidden.npz")
        with self.assertRaises(ValueError):
            pv.inventory(root)
        for forbidden in (self.root / "rlcs-2026", self.root / "test"):
            with self.assertRaises(ValueError):
                pv.inventory(forbidden)

    def test_no_train_or_held_out_discovery_and_duplicate_guard(self):
        root = write_fixture(self.root / "inventory", n_series=3, repeats=1)
        (root / "rlcs-2026").mkdir()
        (root / "rlcs-2026" / "compact-forbidden.parquet").write_text("must not read")
        (root / "rlcs-2024").mkdir()
        (root / "rlcs-2024" / "compact-forbidden.parquet").write_text("must not read")
        self.assertEqual(len(pv.inventory(root)), 1)
        metadata = root / pv.VAL_SEASON / "compact-0000.parquet"
        frame = pd.read_parquet(metadata)
        pd.concat([frame, frame.iloc[:1]], ignore_index=True).to_parquet(metadata, index=False)
        with self.assertRaises(ValueError):
            pv.inventory(root)

    def test_definition_interactions_identical_and_no_equivalence_claim(self):
        a = pv.regulation_contrasts(self.summary, pv.EXTRA_RESPONSES[0])["interaction"]
        b = pv.regulation_contrasts(self.summary, pv.EXTRA_RESPONSES[1])["interaction"]
        for key in ("estimate", "se", "ci_low", "ci_high", "p_value"):
            np.testing.assert_allclose(a[key], b[key], atol=1e-7)
        empty = pv.analyze(pd.DataFrame())
        self.assertIsNone(empty["decisions"]["ot_equivalent_to_late_tied"])


if __name__ == "__main__":
    unittest.main()
