"""Checks for player-relative channels, live boundaries and fixed populations."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tactics_code.style_retrieval import inventory, read_player_slice

from pilot_encoder.dataset import build_dataset, per_frame_features, player_windows
from .fixture import make_fixture


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pilot-dataset-")
        cls.root = make_fixture(Path(cls.temporary.name) / "compact")
        pairs, _ = inventory(cls.root)
        cls.meta = pairs[0][0]
        cls.arrays = read_player_slice(cls.meta)
        cls.config = {"window_frames": 60, "max_windows_per_game": 2, "seed": 42}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_other_player_slot_order_is_invariant(self):
        # Preserve the query at slot 0; exchange teammates and opponents only.
        permutation = [0, 2, 1, 5, 3, 4]
        arrays = copy.deepcopy(self.arrays)
        arrays["players"] = arrays["players"][:, permutation]
        arrays["flags"] = arrays["flags"][:, permutation]
        original, valid = per_frame_features(self.arrays, 0)
        changed, changed_valid = per_frame_features(arrays, 0)
        self.assertEqual(original.shape, (120, 38))
        np.testing.assert_array_equal(valid, changed_valid)
        np.testing.assert_allclose(original, changed, atol=1e-6, rtol=1e-6)

    def test_query_slot_permutation_keeps_player_channels(self):
        permutation = [2, 0, 1, 3, 4, 5]
        arrays = copy.deepcopy(self.arrays)
        arrays["players"] = arrays["players"][:, permutation]
        arrays["flags"] = arrays["flags"][:, permutation]
        original, valid = per_frame_features(self.arrays, 0)
        changed, changed_valid = per_frame_features(arrays, 1)
        np.testing.assert_array_equal(valid, changed_valid)
        np.testing.assert_allclose(original, changed, atol=1e-6, rtol=1e-6)

    def test_no_window_crosses_segment_or_invalid_track(self):
        arrays = copy.deepcopy(self.arrays)
        # Short unequal segments force padding; the missing own track must
        # split a segment instead of bridging the gap with consecutive samples.
        arrays["segment"][:40] = 0
        arrays["segment"][40:80] = 1
        arrays["segment"][80:] = 2
        arrays["players"][15, 0, 0] = np.nan
        config = dict(self.config, max_windows_per_game=20)
        windows = player_windows(self.meta, arrays, 0, config)
        self.assertTrue(windows)
        for values, mask in windows:
            self.assertEqual(values.shape, (60, 38))
            self.assertEqual(mask.shape, (60,))
            self.assertEqual(mask.dtype, np.bool_)
            self.assertGreater(int(mask.sum()), 0)
            self.assertLessEqual(int(mask.sum()), 40)
            self.assertTrue(np.isfinite(values).all())
            self.assertFalse(np.any(np.diff(mask.astype(np.int8)) > 0))

    def test_window_cap_is_deterministic(self):
        first = player_windows(self.meta, self.arrays, 0, self.config)
        second = player_windows(self.meta, self.arrays, 0, self.config)
        self.assertGreater(len(first), 0)
        self.assertLessEqual(len(first), self.config["max_windows_per_game"])
        self.assertEqual(len(first), len(second))
        for (x1, m1), (x2, m2) in zip(first, second):
            np.testing.assert_array_equal(x1, x2)
            np.testing.assert_array_equal(m1, m2)

    def test_missing_context_does_not_drop_valid_player_exposure(self):
        arrays = copy.deepcopy(self.arrays)
        arrays["players"][:, 1:, :7] = np.nan
        arrays["ball"][:] = np.nan
        arrays["flags"][:, 0] = np.nan
        values, valid = per_frame_features(arrays, 0)
        self.assertTrue(valid.all())
        self.assertTrue(np.isfinite(values).all())
        self.assertGreater(len(player_windows(self.meta, arrays, 0, self.config)), 0)

    def test_dataset_keeps_each_usable_player_game(self):
        with tempfile.TemporaryDirectory(prefix="pilot-cache-") as temporary:
            with patch.dict(os.environ, {"TMPDIR": temporary}):
                dataset = build_dataset(self.root, Path(temporary) / "cache", self.config)
            self.assertEqual(len(dataset.games), 960)
            self.assertFalse(dataset.games.duplicated(["identity_id", "season", "replay_id"]).any())
            self.assertEqual(dataset.x.shape[1:], (60, 38))
            self.assertEqual(dataset.masks.shape, dataset.x.shape[:2])
            self.assertEqual(len(dataset.window_games), len(dataset.x))
            self.assertEqual(set(dataset.window_games), set(range(len(dataset.games))))
            self.assertFalse(dataset.games.season.str.contains("2026").any())
            self.assertLessEqual(len(dataset.x), 2 * len(dataset.games))


if __name__ == "__main__":
    unittest.main()
