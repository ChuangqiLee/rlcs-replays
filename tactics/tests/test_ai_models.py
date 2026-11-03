"""CPU-only synthetic checks of model isolation, padding and training guards."""
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch

from ai_experiments.models import make_model, pooled_channels
from ai_experiments.training import GameSampler, fit, embed_games, run_diagnostic


def fixture():
    rng = np.random.default_rng(19)
    rows, x = [], []
    for split, season in (('train', 'rlcs-2024'), ('val', 'rlcs-2025')):
        for game in range(3):
            for identity in range(4):
                rows.append(dict(identity_id=f'p{identity}', split=split, season=season,
                                 replay_id=f'{split}-{game}', series_id=f'{split}-s{game}',
                                 roster_id=f'roster{identity//2}'))
                block = rng.normal(0, .03, (2, 12, 7, 16)).astype('float32')
                block[..., 15] = 1.
                block[..., 0, :3] = identity*.5
                x.append(block)
    x = np.concatenate(x)
    masks = np.ones(x.shape[:2], dtype=bool)
    masks[::2, -2:] = False
    x[~masks] = 0
    pooled = pooled_channels(torch.from_numpy(x)).numpy()
    return SimpleNamespace(x=x, pooled_x=pooled, masks=masks,
                           window_games=np.repeat(np.arange(len(rows)), 2), games=pd.DataFrame(rows))


def configuration(**kwargs):
    config = dict(backbone='transformer', inputs='agents', pooling='meanstd', objective='game',
                  tiny=True, seed=42, masking=False, epochs=1, max_steps=2,
                  batch_identities=2, diagnostic_steps=0, train_budget_seconds=60)
    config.update(kwargs)
    return config


class ModelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_all_components_forward_backward(self):
        data = fixture()
        for backbone, inputs in [('transformer', 'agents'), ('gru', 'agents'), ('mamba', 'agents'),
                                  ('slstm', 'pooled'), ('patch_transformer', 'pooled'),
                                  ('pilot_v1', 'pooled'), ('pilot_v2', 'pooled'),
                                  ('pilot_v3', 'agents'), ('pilot_v4', 'pooled')]:
            with self.subTest(backbone=backbone):
                model = make_model(configuration(backbone=backbone, inputs=inputs, pooling='mean'))
                source = data.pooled_x if inputs == 'pooled' else data.x
                x = torch.tensor(source[:8].reshape(4, 2, *source.shape[1:]))
                masks = torch.tensor(data.masks[:8].reshape(4, 2, -1))
                result = model(x, masks)
                self.assertEqual(result.shape, (4, 128))
                result[:, 0].sum().backward()
                gradients = [p.grad for p in model.parameters() if p.grad is not None]
                self.assertTrue(gradients)
                self.assertTrue(all(torch.isfinite(g).all() for g in gradients))

    def test_padding_and_teammate_permutation(self):
        data = fixture()
        x = torch.tensor(data.x[:8].reshape(4, 2, *data.x.shape[1:]))
        masks = torch.tensor(data.masks[:8].reshape(4, 2, -1))
        for pooling in ('mean', 'meanstd', 'attention'):
            model = make_model(configuration(pooling=pooling)).eval()
            with torch.no_grad():
                expected = model(x, masks)
                permuted = x[:, :, :, [0, 2, 1, 5, 3, 4, 6]]
                self.assertTrue(torch.allclose(expected, model(permuted, masks), atol=1e-6))
                padded = torch.cat((x, torch.full_like(x[:, :1], 999)), 1)
                padded_masks = torch.cat((masks, torch.zeros_like(masks[:, :1])), 1)
                self.assertTrue(torch.allclose(expected, model(padded, padded_masks), atol=1e-6))

    def test_single_window_std_backward(self):
        data = fixture()
        model = make_model(configuration())
        x = torch.tensor(data.x[:4, None])
        masks = torch.tensor(data.masks[:4, None])
        model(x, masks).sum().backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))

    def test_sampler_only_train_distinct_games_and_matched_extras(self):
        data = fixture()
        random = GameSampler(data, 2, 42, 'random')
        cooccurring = GameSampler(data, 2, 42, 'cooccurring')
        for _ in range(10):
            a, la = random.sample()
            b, lb = cooccurring.sample()
            self.assertEqual(len(a), len(b))
            np.testing.assert_array_equal(a[:4], b[:4])
            for indices, labels in ((a, la), (b, lb)):
                self.assertTrue((data.games.iloc[indices].split == 'train').all())
                for pair in indices.reshape(-1, 2):
                    self.assertNotEqual(pair[0], pair[1])
                    self.assertNotEqual(data.games.iloc[pair[0]].series_id, data.games.iloc[pair[1]].series_id)
                self.assertTrue(np.all(np.unique(labels, return_counts=True)[1] == 2))

    def test_fit_never_reads_validation_and_can_embed(self):
        data = fixture()
        valid = data.games.split.to_numpy()[data.window_games] == 'val'
        saved = data.x[valid].copy()
        data.x[valid] = np.nan
        with tempfile.TemporaryDirectory() as directory:
            model, report = fit(data, configuration(pretrain_steps=1), directory)
            self.assertEqual(report['optimizer_steps'], 2)
            self.assertEqual(report['pretraining']['steps'], 1)
            data.x[valid] = saved
            embeddings = embed_games(model, data, batch_size=3)
            self.assertEqual(embeddings.shape, (len(data.games), 128))

    def test_window_game_objective_controls(self):
        data = fixture()
        for objective in ('window', 'game'):
            with tempfile.TemporaryDirectory() as directory:
                _, report = fit(data, configuration(pooling='mean', objective=objective), directory)
            self.assertEqual(report['sampled_windows'], 16)
            self.assertEqual(report['sampled_games'], 8)
            self.assertEqual(report['history'][0]['anchors'], 8 if objective == 'window' else 4)

    def test_overfit_gate_and_forbidden_season(self):
        data = fixture()
        report = run_diagnostic(data, configuration(diagnostic_steps=30))
        self.assertTrue(report['passed'], report)
        self.assertGreater(report['parameter_delta_l2'], 0)
        heldout = report['disjoint_train_series']
        self.assertEqual(heldout['status'], 'available')
        self.assertFalse(set(heldout['fit_series']) & set(heldout['query_series']))
        self.assertTrue((data.games.iloc[heldout['query_game_indices']].split == 'train').all())
        data.games.loc[0, 'season'] = 'rlcs-2026'
        with self.assertRaises((AssertionError, ValueError)):
            GameSampler(data)

    def test_disjoint_diagnostic_reports_unavailable(self):
        data = fixture()
        data.games.loc[data.games.split == 'train', 'series_id'] = 'one-observed-series'
        report = run_diagnostic(data, configuration(diagnostic_steps=0))
        self.assertEqual(report['disjoint_train_series']['status'], 'unavailable')

    def test_production_shape_components(self):
        # Production depth/width and 60-frame shape, bounded synthetic game count.
        x = torch.randn(2, 2, 60, 7, 16)
        x[..., 15] = 1.
        masks = torch.ones((2, 2, 60), dtype=torch.bool)
        for backbone, inputs in [('transformer', 'agents'), ('mamba', 'agents'),
                                  ('slstm', 'pooled'), ('patch_transformer', 'pooled')]:
            with self.subTest(backbone=backbone):
                model = make_model(configuration(backbone=backbone, inputs=inputs, tiny=False))
                model(x, masks).square().sum().backward()
                self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))


if __name__ == '__main__':
    unittest.main()
