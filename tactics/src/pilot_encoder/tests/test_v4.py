"""Synthetic checks for the isolated V4 sLSTM and context sampler."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import TRAIN_SEASONS, VAL_SEASON
from pilot_encoder.models_v4 import TiRexEncoder, contiguous_patch_mask, slstm_scan
from pilot_encoder.models import supervised_contrastive_loss
from pilot_encoder.sampling_v4 import ContextIdentitySampler


class V4ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_exact_production_parameter_count_and_finite_training(self):
        model = TiRexEncoder()
        self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 708992)
        model = TiRexEncoder(tiny=True).train()
        x = torch.randn(8, 60, 38)
        mask = torch.arange(60)[None] < torch.tensor([60, 59, 31, 24, 7, 6, 2, 1])[:, None]
        embedding = model(x, mask)
        loss = supervised_contrastive_loss(embedding, torch.arange(8) // 4)
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(all(parameter.grad is not None and torch.isfinite(parameter.grad).all()
                            for parameter in model.parameters()))

    def test_stabilized_scan_matches_unstabilized_reference_and_gradients(self):
        torch.manual_seed(42)
        gates = (torch.randn(2, 4, 4, 6, dtype=torch.float64) * .2).requires_grad_()
        recurrent = (torch.randn(2, 4, 3, 3, dtype=torch.float64) * .1).requires_grad_()
        mask = torch.tensor([[True, True, True, True], [True, False, True, False]])
        actual = slstm_scan(gates, recurrent, mask)
        h = gates.new_zeros((2, 6))
        c, n = torch.zeros_like(h), torch.zeros_like(h)
        output = []
        for step in range(4):
            # Deliberately use separate head/gate matmuls rather than the
            # implementation's einsum, and no log-domain stabilization.
            feedback = torch.stack([
                torch.cat([h[:, head * 3:(head + 1) * 3] @ recurrent[head, gate].T
                           for head in range(2)], dim=-1) for gate in range(4)], dim=1)
            z, i, f, o = (gates[:, step] + feedback).unbind(dim=1)
            next_c = f.exp() * c + i.exp() * z.tanh()
            next_n = f.exp() * n + i.exp()
            next_h = o.sigmoid() * next_c / next_n
            valid = mask[:, step, None]
            h, c, n = (torch.where(valid, new, old)
                       for new, old in ((next_h, h), (next_c, c), (next_n, n)))
            output.append(torch.where(valid, h, torch.zeros_like(h)))
        expected = torch.stack(output, dim=1)
        torch.testing.assert_close(actual, expected, rtol=1e-10, atol=1e-12)
        actual_grads = torch.autograd.grad(actual.square().sum(), (gates, recurrent), retain_graph=True)
        expected_grads = torch.autograd.grad(expected.square().sum(), (gates, recurrent))
        for actual_grad, expected_grad in zip(actual_grads, expected_grads):
            torch.testing.assert_close(actual_grad, expected_grad, rtol=1e-9, atol=1e-11)

    def test_large_exponential_gates_stay_finite(self):
        gates = torch.zeros(2, 10, 4, 4, requires_grad=True)
        with torch.no_grad():
            gates[:, :, 0] = .5
            gates[0, :, 1:3] = 1000
            gates[1, :, 1] = -1000
            gates[1, :, 2] = 1000
        recurrent = torch.zeros(2, 4, 2, 2, requires_grad=True)
        output = slstm_scan(gates, recurrent, torch.ones(2, 10, dtype=torch.bool))
        self.assertTrue(torch.isfinite(output).all())
        output.square().sum().backward()
        self.assertTrue(torch.isfinite(gates.grad).all())
        self.assertTrue(torch.isfinite(recurrent.grad).all())

    def test_contiguous_mask_keeps_valid_observation(self):
        contents = torch.ones(5, 10, 16)
        lengths = torch.tensor([1, 2, 3, 7, 10])
        valid = torch.arange(10)[None] < lengths[:, None]
        augmented, selected = contiguous_patch_mask(contents, valid, torch.zeros(16), probability=1)
        self.assertEqual(selected.sum(dim=1).tolist(), [0, 1, 2, 2, 2])
        self.assertFalse((selected & ~valid).any())
        self.assertTrue((valid & ~selected).any(dim=1).all())
        self.assertTrue((augmented[selected] == 0).all())
        self.assertTrue((augmented[~selected] == 1).all())
        for row in selected:
            indices = torch.nonzero(row).flatten()
            if len(indices) > 1:
                self.assertTrue(((indices[1:] - indices[:-1]) == 1).all())

    def test_eval_uses_no_augmentation_and_ignores_padding(self):
        torch.manual_seed(42)
        model = TiRexEncoder(tiny=True).eval()
        x = torch.randn(2, 9, 38)
        short_mask = torch.ones(2, 9, dtype=torch.bool)
        long_mask = torch.cat((short_mask, torch.zeros(2, 51, dtype=torch.bool)), dim=1)
        padded = torch.cat((x, torch.full((2, 51, 38), float('nan'))), dim=1)
        state = torch.get_rng_state().clone()
        with torch.inference_mode():
            short, long = model(x, short_mask), model(padded, long_mask)
        self.assertTrue(torch.equal(state, torch.get_rng_state()))
        torch.testing.assert_close(short, long, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(short.norm(dim=-1), torch.ones(2))


class V4SamplerTests(unittest.TestCase):
    def make_games(self):
        return pd.DataFrame([
            {'identity_id': identity, 'replay_id': f'replay-{game}',
             'season': TRAIN_SEASONS[0] if split == 'train' else VAL_SEASON,
             'split': split}
            for split in ('train', 'val')
            for identity in (tuple('ABCDEF') if split == 'train' else ('VAL-ONLY',))
            for game in range(3)])

    def test_only_train_cooccurrences_and_no_false_negatives(self):
        games = self.make_games()
        window_games = np.repeat(np.arange(len(games)), 2)
        features = np.ones((len(window_games), 2), dtype=np.float32)
        features[games.iloc[window_games].split.eq('val')] = np.nan
        sampler = ContextIdentitySampler(window_games, games, 2, 4, 42)
        self.assertNotIn('VAL-ONLY', sampler.identities)
        self.assertEqual(sampler.batch_size, 8)
        self.assertEqual(sampler.steps_per_epoch, 5)
        for _ in range(20):
            indices, labels = sampler.sample()
            self.assertEqual(len(indices), 12)
            self.assertTrue(np.isfinite(features[indices]).all())
            self.assertTrue(games.iloc[window_games[indices]].split.eq('train').all())
            for label in np.unique(labels):
                selected = games.iloc[window_games[indices[labels == label]]]
                self.assertEqual(selected.identity_id.nunique(), 1)
                self.assertGreaterEqual(len(selected), 2)
                self.assertGreaterEqual(selected.replay_id.nunique(), 2)
            for addition in sampler.last_additions:
                anchor = games.iloc[window_games[addition['anchor_window']]]
                context = games.iloc[window_games[addition['context_window']]]
                positive = games.iloc[window_games[addition['positive_window']]]
                self.assertEqual(anchor.replay_id, context.replay_id)
                self.assertNotEqual(anchor.identity_id, context.identity_id)
                self.assertEqual(context.identity_id, positive.identity_id)
                self.assertNotEqual(context.replay_id, positive.replay_id)
        report = sampler.report()
        self.assertEqual(report['context_identities_added'], 40)
        self.assertEqual(report['cooccurring_windows_added'], 40)
        self.assertEqual(report['context_windows_added'], 80)

    def test_reproducible_and_no_additions_when_all_identities_in_base(self):
        games = self.make_games()
        window_games = np.repeat(np.arange(len(games)), 2)
        samplers = [ContextIdentitySampler(window_games, games, 2, 4, 42) for _ in range(2)]
        for _ in range(4):
            left, right = (sampler.sample() for sampler in samplers)
            np.testing.assert_array_equal(left[0], right[0])
            np.testing.assert_array_equal(left[1], right[1])
        full = ContextIdentitySampler(window_games, games, 6, 4, 42)
        indices, labels = full.sample()
        self.assertEqual(len(indices), 24)
        self.assertEqual(len(np.unique(labels)), 6)
        self.assertEqual(full.report()['context_identities_added'], 0)


if __name__ == '__main__':
    unittest.main()
