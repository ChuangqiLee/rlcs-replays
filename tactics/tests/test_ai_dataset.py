"""Synthetic compact data checks; no real compact root is used."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ai_experiments.dataset import (agent_channel_summary, build_dataset,
                                    selected_handcrafted, selected_indices)
from pilot_encoder.dataset import player_windows as pooled_windows
from pilot_encoder.dataset_v3 import player_windows as agent_windows, per_frame_tokens
from pilot_encoder.tests.fixture import make_fixture
from tactics_code.data import iter_compact


def sample_arrays(frames=180):
    players = np.zeros((frames, 6, 8), dtype=np.float32)
    players[:, :, 0] = np.arange(frames)[:, None]
    players[:, :, 6] = 100.
    return {"players": players, "flags": np.zeros((frames, 6, 4), np.float32),
            "ball": np.zeros((frames, 6), np.float32),
            "time": np.arange(frames, dtype=float) / 10,
            "segment": np.zeros(frames, np.int32), "live": np.ones(frames, bool),
            "roles": np.tile(np.arange(3, dtype=np.int8), (frames, 1)),
            "role_uncertain": np.zeros(frames, bool), "touch": np.full(frames, -1, np.int8)}


def sample_meta():
    return dict(season="rlcs-2024", split="train", replay_id="synthetic-game",
                series_id="synthetic-series", roster_id="synthetic-roster", region="EU",
                fps=10., player_ids='["p0","p1","p2","p3","p4","p5"]')


class SelectionTests(unittest.TestCase):
    def test_windows_match_existing_builders_at_discontinuities(self):
        arrays, meta = sample_arrays(), sample_meta()
        arrays["live"][50] = False
        arrays["players"][80, 0, 7] = 1.
        arrays["segment"][100:] = 1
        arrays["time"][120:] += .3
        config = dict(window_frames=60, max_windows_per_game=8, selection_seed=42, seed=42)
        selected = selected_indices(meta, arrays, 0, config)
        tokens, _ = per_frame_tokens(arrays, 0)
        expected = agent_windows(meta, arrays, 0, config)
        expected_pooled = pooled_windows(meta, arrays, 0, config)
        self.assertEqual(len(selected), len(expected))
        self.assertEqual(len(selected), len(expected_pooled))
        for indices, (values, mask), (_, pooled_mask) in zip(selected, expected, expected_pooled):
            np.testing.assert_array_equal(values[mask], tokens[indices])
            np.testing.assert_array_equal(mask, pooled_mask)
            self.assertTrue(np.all(np.diff(indices) == 1))
            self.assertEqual(len(np.unique(arrays["segment"][indices])), 1)
            self.assertTrue(np.all(np.diff(arrays["time"][indices]) <= .15))
        other = selected_indices(meta, arrays, 0, dict(config, seed=44))
        for left, right in zip(selected, other):
            np.testing.assert_array_equal(left, right)

    def test_matched_handcrafted_rates_do_not_bridge_unobserved_gap(self):
        arrays, meta = sample_arrays(), sample_meta()
        arrays["players"][:5, 0, 6] = 200
        arrays["players"][5:, 0, 6] = 0
        arrays["flags"][5:, 0, 0] = 1
        row = selected_handcrafted(meta, arrays, 0, [np.array([0, 1]), np.array([10, 11])])
        self.assertEqual(row["f_boost_spent_per_second"], 0.)
        self.assertEqual(row["f_dodge_per_minute"], 0.)
        self.assertAlmostEqual(row["live_seconds"], .4)

    def test_exact_agent_channel_summary_ignores_teammate_opponent_slot_order(self):
        values = np.random.default_rng(42).normal(size=(11, 7, 16)).astype(np.float32)
        selected = np.array([0, 3, 4, 7, 10])
        permutation = [0, 2, 1, 5, 3, 4, 6]
        a = agent_channel_summary(values, selected)
        b = agent_channel_summary(values[:, permutation], selected)
        self.assertEqual(a.shape, (128,))
        np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-7)
        np.testing.assert_allclose(a[:16], values[selected, 0].mean(0))


class CompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ai-data-tests-", dir="/tmp")
        cls.root = Path(cls.temp.name)
        cls.compact = make_fixture(cls.root / "synthetic", frames=100)
        cls.config = dict(window_frames=60, max_windows_per_game=2, selection_seed=42)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_adapter_preserves_population_and_poison_season_unopened(self):
        opened = []
        original_load = np.load
        def load(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotIn("2026", str(path))
            return original_load(path, *args, **kwargs)
        with patch.dict(os.environ, {"TMPDIR": str(self.root)}), patch("numpy.load", side_effect=load):
            dataset = build_dataset(self.compact, self.root / "full-cache", self.config)
        self.assertEqual(len(dataset.games), 960)
        self.assertEqual(len(dataset.x), 1920)
        self.assertEqual(dataset.matched_handcrafted.shape, (960, 31))
        self.assertEqual(dataset.summaries.shape, (960, 76))
        self.assertEqual(dataset.agent_summaries.shape, (960, 128))
        self.assertEqual(set(dataset.games.season), {"rlcs-21-22", "rlcs-22-23", "rlcs-2024", "rlcs-2025"})
        self.assertTrue(Path(dataset.report["selection_file"]).is_file())
        self.assertEqual(len(opened), 4)
        self.assertFalse(dataset.report["test_opened"])

    def test_train_only_never_materializes_validation_payload(self):
        opened = []
        def guarded_iter(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotIn("2025", str(path))
            self.assertNotIn("2026", str(path))
            yield from iter_compact(path, *args, **kwargs)
        with patch.dict(os.environ, {"TMPDIR": str(self.root)}), \
                patch("ai_experiments.dataset.iter_compact", side_effect=guarded_iter):
            dataset = build_dataset(self.compact, self.root / "train-cache", self.config, train_only=True)
        self.assertEqual(len(dataset.games), 720)
        self.assertEqual(set(dataset.games.split), {"train"})
        self.assertEqual({row["split"] for row in dataset.metadata}, {"train"})
        self.assertEqual(len(opened), 3)

    def test_forbidden_metadata_rejected_before_npz_payload(self):
        directory = self.root / "mislabeled"
        allowed = directory / "rlcs-2024"
        allowed.mkdir(parents=True)
        row = sample_meta()
        row["season"] = "rlcs-2026"
        pd.DataFrame([row]).to_parquet(allowed / "compact-000.parquet")
        with patch.dict(os.environ, {"TMPDIR": str(self.root)}), \
                patch("numpy.load", side_effect=AssertionError("Must not open payload")):
            with self.assertRaisesRegex(ValueError, "Forbidden"):
                build_dataset(directory, self.root / "rejected-cache", self.config)


if __name__ == "__main__":
    unittest.main()
