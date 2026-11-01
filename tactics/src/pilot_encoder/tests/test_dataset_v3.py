"""Synthetic parity checks for V3's isolated multi-agent dataset extension."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tactics_code.style_retrieval import read_player_slice
from pilot_encoder import dataset as frozen
from pilot_encoder import dataset_v3 as agents
from .fixture import make_fixture


class MultiAgentDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='pilot-agents-')
        cls.root = make_fixture(Path(cls.temporary.name) / 'compact', frames=180)
        pairs, _ = frozen.safe_inventory(cls.root)
        cls.meta = pairs[0][0]
        cls.arrays = read_player_slice(cls.meta)
        cls.config = {'window_frames': 60, 'max_windows_per_game': 2, 'seed': 42}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_available_agent_features_recover_original_inputs(self):
        tokens, valid = agents.per_frame_tokens(self.arrays, 1)
        original, original_valid = frozen.per_frame_features(self.arrays, 1)
        np.testing.assert_array_equal(valid, original_valid)
        np.testing.assert_array_equal(tokens[:, 0, :15], original[:, :15])
        np.testing.assert_array_equal(tokens[:, 6, :6], original[:, 15:21])
        np.testing.assert_array_equal(tokens[:, 6, 15], original[:, 21])
        self.assertTrue((tokens[:, :6, 15] == 1).all())
        self.assertTrue((tokens[:, 6, 6:15] == 0).all())
        for group, begin in ((slice(1, 3), 22), (slice(3, 6), 30)):
            available = tokens[:, group, 15]
            count = available.sum(axis=1, keepdims=True)
            pooled = tokens[:, group, :7].sum(axis=1) / np.maximum(count, 1)
            np.testing.assert_allclose(pooled, original[:, begin:begin + 7], atol=1e-7)
            np.testing.assert_array_equal(available.mean(axis=1), original[:, begin + 7])

    def test_missing_demolished_agents_and_unknown_flags_are_imputed(self):
        arrays = copy.deepcopy(self.arrays)
        arrays['players'][:, 1, 7] = 1
        arrays['players'][:, 4, 2] = np.nan
        arrays['ball'][:, 3] = np.nan
        arrays['flags'][:, 2, 1] = np.nan
        arrays['flags'][:, 0, 0] = 3
        tokens, valid = agents.per_frame_tokens(arrays, 0)
        self.assertTrue(valid.all())
        self.assertTrue(np.isfinite(tokens).all())
        np.testing.assert_array_equal(tokens[:, [1, 4, 6]], 0)
        np.testing.assert_array_equal(tokens[:, 2, 8], 0)
        np.testing.assert_array_equal(tokens[:, 2, 12], 0)
        np.testing.assert_array_equal(tokens[:, 0, 7], 1)
        np.testing.assert_array_equal(tokens[:, 0, 11], 1)
        np.testing.assert_array_equal(tokens[:, 0, 15], 1)

    def test_slot_changes_only_permute_same_role_tokens(self):
        permutation = [0, 2, 1, 5, 3, 4]
        arrays = copy.deepcopy(self.arrays)
        arrays['players'] = arrays['players'][:, permutation]
        arrays['flags'] = arrays['flags'][:, permutation]
        original, valid = agents.per_frame_tokens(self.arrays, 0)
        changed, changed_valid = agents.per_frame_tokens(arrays, 0)
        np.testing.assert_array_equal(valid, changed_valid)
        np.testing.assert_array_equal(changed, original[:, permutation + [6]])
        # Moving the focal player within its team preserves its first token.
        permutation = [2, 0, 1, 3, 4, 5]
        arrays['players'] = self.arrays['players'][:, permutation]
        arrays['flags'] = self.arrays['flags'][:, permutation]
        moved, moved_valid = agents.per_frame_tokens(arrays, 1)
        np.testing.assert_array_equal(valid, moved_valid)
        np.testing.assert_array_equal(moved, original[:, [0, 2, 1, 3, 4, 5, 6]])

    def test_window_selection_matches_frozen_discontinuities_and_hash_cap(self):
        arrays = copy.deepcopy(self.arrays)
        arrays['players'][15, 0, 0] = np.nan
        arrays['live'][41] = False
        arrays['segment'][80:120] = 1
        arrays['segment'][120:] = 2
        arrays['time'][130] = arrays['time'][129]
        arrays['time'][150:] += 1
        for cap in (2, 8, 100):
            config = dict(self.config, max_windows_per_game=cap)
            original = frozen.player_windows(self.meta, arrays, 0, config)
            actual = agents.player_windows(self.meta, arrays, 0, config)
            self.assertEqual(len(actual), len(original))
            for (old_x, old_mask), (new_x, new_mask) in zip(original, actual):
                np.testing.assert_array_equal(old_mask, new_mask)
                np.testing.assert_array_equal(old_x[:, :15], new_x[:, 0, :15])
                self.assertFalse(new_x[~new_mask].any())
                self.assertTrue(np.isfinite(new_x).all())

    def test_dataset_population_source_and_every_window_match_frozen(self):
        with tempfile.TemporaryDirectory(prefix='pilot-agent-cache-') as temporary:
            with patch.dict(os.environ, {'TMPDIR': temporary}):
                original = frozen.build_dataset(self.root, Path(temporary) / 'base', self.config)
                with patch.object(agents, 'iter_compact', wraps=agents.iter_compact) as reader:
                    actual = agents.build_dataset(self.root, Path(temporary) / 'agents', self.config)
            for call in reader.call_args_list:
                path = Path(call.args[0])
                self.assertEqual(path.suffix, '.npz')
                self.assertIn(path.parent.name, frozen.ALLOWED_SEASONS)
            pd.testing.assert_frame_equal(actual.games, original.games)
            self.assertEqual(actual.metadata, original.metadata)
            np.testing.assert_array_equal(actual.window_games, original.window_games)
            np.testing.assert_array_equal(actual.masks, original.masks)
            np.testing.assert_array_equal(actual.x[:, :, 0, :15], original.x[:, :, :15])
            self.assertEqual(actual.x.shape, (1920, 60, 7, 16))
            for key in ('available_replays', 'processed_replays', 'player_games',
                        'player_games_by_season', 'windows', 'windows_by_split',
                        'input_files', 'replay_ids', 'compact_series_completeness_certified', 'test_opened'):
                self.assertEqual(actual.report[key], original.report[key], key)


if __name__ == '__main__':
    unittest.main()
