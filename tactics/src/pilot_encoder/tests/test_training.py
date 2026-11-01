"""Synthetic checks for identity sampling and masked neural representations."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import TRAIN_SEASONS, VAL_SEASON

from pilot_encoder.models import make_model, supervised_contrastive_loss
from pilot_encoder.training import IdentitySampler, _validate_shapes


class TrainingTests(unittest.TestCase):
    def test_sampler_uses_train_only_and_different_games_for_positives(self):
        games = pd.DataFrame([
            {"identity_id": identity, "replay_id": f"{identity}-{split}-{game}",
             "season": TRAIN_SEASONS[0] if split == "train" else VAL_SEASON,
             "split": split}
            for identity in ("A", "B", "C")
            for split in ("train", "val") for game in range(3)
        ])
        window_games = np.repeat(np.arange(len(games)), 2)
        # Poison every validation feature. The same shape validator and sampler
        # used by train_model must leave those payloads out of training batches.
        features = np.ones((len(window_games), 60, 38), dtype=np.float32)
        masks = np.ones(features.shape[:2], dtype=np.bool_)
        validation_windows = games.iloc[window_games].split.to_numpy() == "val"
        features[validation_windows] = np.nan
        _validate_shapes(features, masks, window_games)
        sampler = IdentitySampler(window_games, games, batch_identities=3,
                                  windows_per_identity=4, seed=42)
        for _ in range(10):
            indices, labels = sampler.sample()
            sampled_games = games.iloc[window_games[indices]]
            self.assertTrue(sampled_games.split.eq("train").all())
            self.assertTrue(np.isfinite(features[indices]).all())
            for label in np.unique(labels):
                same = sampled_games.iloc[np.flatnonzero(labels == label)]
                self.assertEqual(same.identity_id.nunique(), 1)
                self.assertGreaterEqual(same.replay_id.nunique(), 2)

    def test_encoder_ignores_right_padding_values(self):
        torch.manual_seed(42)
        torch.set_num_threads(1)
        signal = torch.randn(2, 9, 38)
        short_mask = torch.ones((2, 9), dtype=torch.bool)
        long_mask = torch.cat((short_mask, torch.zeros((2, 4), dtype=torch.bool)), dim=1)
        padded = torch.cat((signal, 999 * torch.ones((2, 4, 38))), dim=1)
        for variant in ("v1", "v2"):
            with self.subTest(variant=variant), torch.inference_mode():
                model = make_model(variant, input_dim=38, tiny=True).eval()
                short, long = model(signal, short_mask), model(padded, long_mask)
                torch.testing.assert_close(short, long, rtol=1e-5, atol=1e-6)
                torch.testing.assert_close(short.norm(dim=1), torch.ones(2), rtol=1e-5, atol=1e-6)

    def test_supcon_requires_positive_partner_and_is_label_invariant(self):
        torch.manual_seed(42)
        raw = torch.randn(8, 16, requires_grad=True)
        embedding = torch.nn.functional.normalize(raw, dim=1)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        loss = supervised_contrastive_loss(embedding, labels)
        relabelled = supervised_contrastive_loss(embedding, 17 - labels)
        torch.testing.assert_close(loss, relabelled)
        loss.backward()
        self.assertTrue(torch.isfinite(raw.grad).all())
        with self.assertRaises(ValueError):
            supervised_contrastive_loss(embedding, torch.arange(8))


if __name__ == "__main__":
    unittest.main()
