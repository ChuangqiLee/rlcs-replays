"""Synthetic V3 tests: scan algebra, masking, agent symmetry, fixed size."""
from __future__ import annotations

import unittest

import torch

from pilot_encoder.models import supervised_contrastive_loss
from pilot_encoder.models_v3 import UniTrajEncoder, selective_scan, reverse_valid_prefix


def sequential_scan(log_transition, value):
    previous = torch.zeros_like(value[:, 0])
    states = []
    for index in range(value.shape[1]):
        previous = log_transition[:, index].exp() * previous + value[:, index]
        states.append(previous)
    return torch.stack(states, dim=1)


class V3ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_parallel_scan_matches_sequential_values_and_gradients(self):
        torch.manual_seed(42)
        for length in (1, 7, 16, 60):
            with self.subTest(length=length):
                log_a = -torch.rand(2, length, 3, 4, dtype=torch.float64)
                # Zero log transition and zero input represent padded steps.
                log_a[:, max(1, length - 2):] = 0
                value = torch.randn_like(log_a)
                value[:, max(1, length - 2):] = 0
                log_a.requires_grad_()
                value.requires_grad_()
                upstream = torch.randn_like(value)
                actual = selective_scan(log_a, value)
                expected = sequential_scan(log_a, value)
                torch.testing.assert_close(actual, expected, atol=1e-12, rtol=1e-12)
                actual_gradient = torch.autograd.grad((actual * upstream).sum(), (log_a, value))
                expected_gradient = torch.autograd.grad((expected * upstream).sum(), (log_a, value))
                for a, b in zip(actual_gradient, expected_gradient):
                    torch.testing.assert_close(a, b, atol=1e-12, rtol=1e-12)

    def test_scan_extreme_decays_and_gradcheck(self):
        log_a = torch.tensor([0., -1e-8, -10000., -0.1, 0.], dtype=torch.float64).reshape(1, 5, 1, 1)
        value = torch.randn_like(log_a)
        log_a.requires_grad_()
        value.requires_grad_()
        self.assertTrue(torch.autograd.gradcheck(selective_scan, (log_a, value)))
        self.assertTrue(torch.isfinite(selective_scan(log_a, value)).all())

    def test_parameters_and_padding_invariance(self):
        self.assertEqual(sum(p.numel() for p in UniTrajEncoder().parameters()), 1121408)
        torch.manual_seed(42)
        model = UniTrajEncoder(tiny=True).eval()
        signal = torch.randn(2, 9, 7, 16)
        signal[..., -1] = 1
        short_mask = torch.ones((2, 9), dtype=torch.bool)
        padded = torch.cat((signal, torch.full((2, 4, 7, 16), float('nan'))), dim=1)
        long_mask = torch.cat((short_mask, torch.zeros((2, 4), dtype=torch.bool)), dim=1)
        with torch.inference_mode():
            short, long = model(signal, short_mask), model(padded, long_mask)
        torch.testing.assert_close(short, long, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(short.norm(dim=-1), torch.ones(2))

    def test_agent_order_invariance_and_missing_agent_ghost(self):
        torch.manual_seed(42)
        model = UniTrajEncoder(tiny=True).eval()
        signal = torch.randn(2, 9, 7, 16)
        signal[..., -1] = 1
        signal[:, :, 1] = 0
        mask = torch.ones((2, 9), dtype=torch.bool)
        with torch.inference_mode():
            expected = model(signal, mask)
            actual = model(signal[:, :, [0, 2, 1, 5, 3, 4, 6]], mask)
            token = model.agent_tokens(signal, mask)
            absent = model.ghost + model.roles.weight[1]
        torch.testing.assert_close(expected, actual, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(token[:, :, 1], absent.expand(2, 9, -1))

    def test_training_ghost_probability_and_query_exemption(self):
        torch.manual_seed(42)
        model = UniTrajEncoder(tiny=True)
        signal = torch.randn(32, 60, 7, 16)
        signal[..., -1] = 1
        mask = torch.ones((32, 60), dtype=torch.bool)
        model.eval()
        natural = model.agent_tokens(signal, mask)
        torch.testing.assert_close(model.agent_tokens(signal, mask), natural)
        model.train()
        masked = model.agent_tokens(signal, mask)
        torch.testing.assert_close(masked[:, :, 0], natural[:, :, 0])
        fraction = (masked[:, :, 1:] != natural[:, :, 1:]).any(dim=-1).float().mean().item()
        self.assertGreater(fraction, 0.13)
        self.assertLess(fraction, 0.17)
        expected_ghost = model.ghost + model.roles(model.role_ids)
        changed = (masked != natural).any(dim=-1)
        torch.testing.assert_close(masked[changed], expected_ghost.expand_as(masked)[changed])

    def test_valid_prefix_reversal_and_train_gradients(self):
        signal = torch.arange(12.).reshape(2, 6, 1)
        mask = torch.tensor([[True, True, False, False, False, False], [True] * 6])
        expected = torch.tensor([1., 0., 2., 3., 4., 5., 11., 10., 9., 8., 7., 6.]).reshape(2, 6, 1)
        torch.testing.assert_close(reverse_valid_prefix(signal, mask), expected)
        torch.manual_seed(42)
        model = UniTrajEncoder(tiny=True).train()
        x = torch.randn(4, 12, 7, 16)
        x[..., -1] = 1
        mask = torch.ones((4, 12), dtype=torch.bool)
        mask[0, 8:] = False
        loss = supervised_contrastive_loss(model(x, mask), torch.tensor([0, 0, 1, 1]))
        loss.backward()
        for name, parameter in model.named_parameters():
            with self.subTest(parameter=name):
                self.assertIsNotNone(parameter.grad)
                self.assertTrue(torch.isfinite(parameter.grad).all())


if __name__ == '__main__':
    unittest.main()
