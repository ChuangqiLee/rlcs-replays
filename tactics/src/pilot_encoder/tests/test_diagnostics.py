"""Synthetic diagnostic checks; never open compact data or alter training RNG."""
import math
import unittest

import torch
from torch.nn import functional as F

from pilot_encoder.diagnostics import batch_diagnostics
from pilot_encoder.models import supervised_contrastive_loss


class DiagnosticTests(unittest.TestCase):
    def test_uniform_loss_does_not_identify_embedding_collapse(self):
        labels = torch.arange(4).repeat_interleave(4)
        mask = torch.ones(16, 3, dtype=torch.bool)
        x = torch.zeros(16, 3, 38)
        collapsed = F.normalize(torch.ones(16, 128), dim=-1)
        orthogonal = torch.eye(128)[:16]
        rows = [batch_diagnostics(z, labels, x, mask) for z in (collapsed, orthogonal)]
        for z, row in zip((collapsed, orthogonal), rows):
            self.assertAlmostEqual(float(supervised_contrastive_loss(z, labels)), math.log(15), places=5)
            self.assertAlmostEqual(row['mean_softmax_entropy'], math.log(15), places=5)
            self.assertEqual(row['positive_counts_min'], 3)
        self.assertEqual(rows[0]['embedding_std_mean'], 0.)
        self.assertGreater(rows[1]['embedding_std_mean'], 0.)
        self.assertAlmostEqual(rows[0]['negative_cosine_mean'], 1., places=5)
        self.assertEqual(rows[1]['negative_cosine_mean'], 0.)

    def test_observation_preserves_rng_gradients_and_masks_padding(self):
        torch.manual_seed(42)
        raw = torch.randn(8, 128, requires_grad=True)
        z = F.normalize(raw, dim=-1)
        labels = torch.arange(4).repeat_interleave(2)
        mask = torch.tensor([[True, True, False]]).expand(8, -1)
        x = torch.ones(8, 3, 7, 16)
        x[:, -1] = 999.
        before = torch.get_rng_state().clone()
        loss = supervised_contrastive_loss(z, labels)
        expected = torch.autograd.grad(loss, raw, retain_graph=True)[0]
        row = batch_diagnostics(z, labels, x, mask)
        actual = torch.autograd.grad(loss, raw)[0]
        torch.testing.assert_close(before, torch.get_rng_state(), rtol=0, atol=0)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        self.assertEqual(row['input_channel_abs_max'], [1.] * 16)
        self.assertEqual(row['valid_frames_min'], 2)


if __name__ == '__main__':
    unittest.main()
