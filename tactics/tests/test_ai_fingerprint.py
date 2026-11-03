"""CPU checks for the window cache, dev-split relabeling and fingerprint model."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
import torch

from ai_experiments.cache import CTX_COLUMNS, build, goal_events, load_cache
from ai_experiments.dataset import build_dataset
from ai_experiments.devrun import BASE, Sampler, relabel
from ai_experiments.fingerprint import CosineClassifier, FingerprintModel, Standardizer, supcon
from pilot_encoder.tests.fixture import make_fixture
from tactics_code.screen import TRAIN_SEASONS, VAL_SEASON


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        os.environ['TMPDIR'] = str(root)
        cls.compact = make_fixture(root / 'synthetic', frames=120)
        cls.config = dict(window_frames=60, max_windows_per_game=64, selection_seed=42)
        cls.report = build(cls.compact, root / 'cache', cls.config, workers=2)
        cls.data = load_cache(root / 'cache', root / 'scratch')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_matches_frozen_builder(self):
        ref = build_dataset(self.compact, Path(self.tmp.name) / 'ref', self.config)
        d = self.data
        self.assertEqual(len(ref.games), len(d.games))
        np.testing.assert_array_equal(ref.games.identity_id.to_numpy(), d.games.identity_id.to_numpy())
        np.testing.assert_array_equal(ref.window_games, d.window_games)
        np.testing.assert_array_equal(ref.masks, d.masks)
        self.assertLess(np.abs(ref.x - d.x[:].astype(np.float32)).max(), 1e-3)
        self.assertLess(np.abs(ref.pooled_x - d.pooled_x[:].astype(np.float32)).max(), 1e-3)
        np.testing.assert_allclose(ref.summaries, d.summaries, atol=1e-6)
        np.testing.assert_allclose(ref.agent_summaries, d.agent_summaries, atol=1e-6)

    def test_context_columns(self):
        d = self.data
        self.assertEqual(d.ctx.shape, (len(d.masks), len(CTX_COLUMNS)))
        n_valid = d.ctx[:, CTX_COLUMNS.index('n_valid')]
        np.testing.assert_array_equal(n_valid, d.masks.sum(1))
        self.assertTrue((d.ctx[:, CTX_COLUMNS.index('t_end')] >= d.ctx[:, CTX_COLUMNS.index('t_start')]).all())
        self.assertTrue((d.ctx[:, CTX_COLUMNS.index('dt_own_goal')] > 0).all())

    def test_goal_events_sign(self):
        arrays = dict(score_diff=np.array([0, 0, 1, 1, 0, np.nan, 0, -1.]), time=np.arange(8.))
        times, delta = goal_events(arrays)
        np.testing.assert_array_equal(times, [2., 4., 7.])
        np.testing.assert_array_equal(delta, [1., -1., -1.])

    def test_report_never_opens_test(self):
        self.assertFalse(self.report['test_opened'])
        self.assertTrue(all('2026' not in f['path'] for f in self.report['input_files']))


class RelabelTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for season in TRAIN_SEASONS + (VAL_SEASON,):
            for g in range(3):
                rows.append(dict(identity_id='p', season=season, split='val' if season == VAL_SEASON else 'train',
                                 replay_id=f'{season}-{g}', series_id=f'{season}-s', roster_id='r', region='Europe'))
        self.games = pd.DataFrame(rows)
        self.metadata = [dict(season=r['season'], split=r['split'], player_ids='[]') for r in rows]

    def test_dev_drops_2025_and_relabels_dev_season(self):
        games, keep, metadata, train_seasons, eval_season = relabel(self.games, self.metadata, 'dev', 'rlcs-2024')
        self.assertNotIn(VAL_SEASON, set(games.season_original))
        self.assertEqual(keep.sum(), 9)
        self.assertEqual(set(games[games.split == 'val'].season_original), {'rlcs-2024'})
        self.assertEqual(set(games[games.split == 'val'].season), {VAL_SEASON})
        self.assertEqual(set(games[games.split == 'train'].season_original), set(train_seasons))
        self.assertEqual(eval_season, 'rlcs-2024')
        self.assertTrue(all(m['season'] != VAL_SEASON or m['season_original'] == 'rlcs-2024' for m in metadata))

    def test_final_keeps_everything(self):
        games, keep, metadata, train_seasons, eval_season = relabel(self.games, self.metadata, 'final', 'rlcs-2024')
        self.assertTrue(keep.all())
        self.assertEqual(eval_season, VAL_SEASON)
        self.assertEqual(tuple(train_seasons), TRAIN_SEASONS)


class ModelTests(unittest.TestCase):
    def test_forward_and_losses(self):
        torch.manual_seed(0)
        cfg = dict(BASE, width=16, heads=2, w_supcon=1., margin=.2)
        std = Standardizer(torch.zeros(16), torch.ones(16))
        model = FingerprintModel(cfg, n_identities=5, standardizer=std)
        x = torch.randn(8, 12, 7, 16)
        x[..., 15] = 1.
        mask = torch.ones(8, 12, dtype=torch.bool)
        mask[::2, -3:] = False
        bag = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        game_labels = torch.tensor([0, 0, 1, 1])
        loss, terms, g = model(x, mask, bag, 4, game_labels[bag], game_labels)
        self.assertTrue(torch.isfinite(loss))
        self.assertEqual(g.shape, (4, 128))
        torch.testing.assert_close(g.norm(dim=-1), torch.ones(4))
        for key in ('window_ce', 'game_ce', 'supcon', 'game_acc'):
            self.assertIn(key, terms)
        loss.backward()
        grads = [p.grad for p in model.parameters() if p.requires_grad and p.grad is not None]
        self.assertTrue(all(torch.isfinite(g).all() for g in grads))

    def test_backbones(self):
        for temporal in ('transformer', 'gru', 'mamba'):
            for inputs in ('agents', 'pooled'):
                cfg = dict(BASE, width=16, heads=2, temporal=temporal, inputs=inputs)
                model = FingerprintModel(cfg, 3, Standardizer(torch.zeros(16 if inputs == 'agents' else 38),
                                                              torch.ones(16 if inputs == 'agents' else 38)))
                x = torch.randn(4, 10, 7, 16)
                x[..., 15] = 1.
                mask = torch.ones(4, 10, dtype=torch.bool)
                z = model.encoder.window_embeddings(x, mask)
                self.assertEqual(z.shape, (4, 128))

    def test_margin_only_affects_target(self):
        clf = CosineClassifier(8, 3, scale=1., margin=.3)
        z = torch.nn.functional.normalize(torch.randn(2, 8), dim=-1)
        labels = torch.tensor([0, 2])
        clf.train()
        with_margin = clf(z, labels)
        plain = clf(z)
        off = torch.ones_like(plain, dtype=torch.bool)
        off[torch.arange(2), labels] = False
        torch.testing.assert_close(with_margin[off], plain[off])
        self.assertTrue((with_margin[torch.arange(2), labels] <= plain[torch.arange(2), labels]).all())

    def test_supcon_uniform_value(self):
        z = torch.nn.functional.normalize(torch.ones(6, 4), dim=-1)
        labels = torch.tensor([0, 0, 1, 1, 2, 2])
        self.assertAlmostEqual(float(supcon(z, labels)), float(np.log(5)), places=5)


class SamplerTests(unittest.TestCase):
    def test_labels_align_with_games(self):
        rows = []
        for identity in range(4):
            for g in range(3):
                rows.append(dict(identity_id=f'p{identity}', split='train', season='rlcs-2024',
                                 replay_id=f'r{identity}{g}', series_id=f's{g}', roster_id='r', region='Europe'))
        rows.append(dict(identity_id='single', split='train', season='rlcs-2024', replay_id='x', series_id='sx',
                         roster_id='r', region='Europe'))
        games = pd.DataFrame(rows)
        windows = [np.arange(i * 3, i * 3 + 3) for i in range(len(games))]
        sampler = Sampler(games, windows, dict(BASE, batch_identities=3, windows_per_game=2), np.random.default_rng(1))
        self.assertEqual(sampler.n_classes, 5)
        self.assertNotIn('single', sampler.pairable)
        rows_, bag, labels, game_rows = sampler.sample()
        self.assertEqual(len(game_rows), 6)
        for b, row in zip(bag, rows_):
            self.assertIn(row, windows[game_rows[b]])
        for i in range(0, 6, 2):
            self.assertEqual(labels[i], labels[i + 1])
            self.assertNotEqual(game_rows[i], game_rows[i + 1])
            self.assertEqual(games.identity_id[game_rows[i]], sampler.identities[labels[i]])


if __name__ == '__main__':
    unittest.main()
