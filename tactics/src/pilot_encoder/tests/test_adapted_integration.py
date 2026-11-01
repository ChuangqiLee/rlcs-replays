"""V3/V4 runner guards, fixed settings, and fitting with poisoned validation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from tactics_code.screen import TRAIN_SEASONS, VAL_SEASON
from pilot_encoder.run import fixed_config as old_config
from pilot_encoder.run_adapted import fixed_config
from pilot_encoder.training_adapted import train_model
from .fixture import make_fixture


ROOT = Path(__file__).resolve().parents[3]


class AdaptedIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='pilot-adapted-cli-')
        cls.fixture = make_fixture(Path(cls.temporary.name) / 'compact')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self, variant, *arguments, overrides=None):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        environment.pop('SLURM_JOB_ID', None)
        environment.pop('PILOT_START_EPOCH', None)
        environment['PYTHONPATH'] = str(ROOT / 'src')
        environment.update(overrides or {})
        return subprocess.run([sys.executable, '-B', '-m', 'pilot_encoder.run_adapted',
                               '--variant', variant, *map(str, arguments)],
                              cwd=ROOT, env=environment, text=True,
                              capture_output=True, timeout=30)

    def test_same_fixed_protocol_and_no_config_mutation(self):
        frozen = old_config('v1')
        for variant in ('v3', 'v4'):
            config = fixed_config(variant)
            for key in ('seed', 'window_frames', 'max_windows_per_game', 'epochs',
                        'batch_identities', 'windows_per_identity', 'permutations',
                        'bootstrap', 'train_budget_seconds', 'total_budget_seconds',
                        'learning_rate', 'weight_decay', 'gradient_clip_norm',
                        'loss', 'temperature', 'embedding_dim', 'early_stopping',
                        'selection', 'input_scaling', 'pass_threshold'):
                self.assertEqual(config[key], frozen[key], key)
            self.assertEqual(config['variant_family'], ['v1', 'v2', 'v3', 'v4'])
            self.assertTrue(config['report_all_variants'])
        self.assertEqual(old_config('v1'), frozen)

    def test_new_production_paths_refuse_before_opening_data(self):
        for variant in ('v3', 'v4'):
            with self.subTest(variant=variant):
                result = self.invoke(variant, '--compact', '/nonexistent-pilot-input')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('must run inside SLURM', result.stderr)
                self.assertNotIn('FileNotFoundError', result.stderr)

    def test_staging_and_elapsed_budget_reports_for_both_variants(self):
        with tempfile.TemporaryDirectory(prefix='pilot-adapted-report-') as temporary:
            root = Path(temporary)
            for variant in ('v3', 'v4'):
                with self.subTest(variant=variant):
                    common = ('--synthetic-smoke', '--device', 'cpu', '--compact', self.fixture)
                    out = root / f'{variant}.json'
                    staged = root / variant
                    result = self.invoke(variant, *common, '--out', out, '--stage-to', staged)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(out.read_text())
                    self.assertEqual(report['status'], 'staged')
                    self.assertEqual(report['staging']['replays'], 160)
                    self.assertFalse(report['pass_decision'])
                    self.assertFalse((staged / 'rlcs-2026').exists())
                    result = self.invoke(variant, *common, '--out', out,
                                         overrides={'PILOT_START_EPOCH': '0'})
                    self.assertNotEqual(result.returncode, 0)
                    report = json.loads(out.read_text())
                    self.assertEqual(report['status'], 'failed')
                    self.assertEqual(report['error']['type'], 'TimeoutError')
                    self.assertFalse(report['pass_decision'])
                    self.assertFalse(report['test_opened'])

    def test_both_trainers_never_read_validation_feature_payload(self):
        torch.set_num_threads(1)
        games = pd.DataFrame([
            dict(identity_id=identity, replay_id=f'{split}-{game}',
                 season=TRAIN_SEASONS[0] if split == 'train' else VAL_SEASON, split=split)
            for identity in ('A', 'B') for split, count in (('train', 2), ('val', 1))
            for game in range(count)
        ])
        window_games = np.repeat(np.arange(len(games)), 2)
        validation = games.iloc[window_games].split.to_numpy() == 'val'
        masks = np.ones((len(window_games), 60), dtype=np.bool_)
        for variant in ('v3', 'v4'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory(prefix='pilot-train-only-') as temporary:
                shape = (len(window_games), 60, 7, 16) if variant == 'v3' else (len(window_games), 60, 38)
                values = np.random.default_rng(12).normal(size=shape).astype(np.float32)
                if variant == 'v3':
                    values[..., -1] = 1
                values[validation] = np.nan
                with patch.dict(os.environ, {'TMPDIR': temporary}):
                    model, report = train_model(values, masks, window_games, games,
                                                fixed_config(variant, synthetic=True),
                                                Path(temporary) / variant, 'cpu')
                self.assertEqual(report['optimizer_steps'], 1)
                self.assertEqual(report['completed_epochs'], 1)
                self.assertEqual(report['train_windows'], 8)
                self.assertFalse(report['test_opened'])
                self.assertFalse(model.training)
                self.assertTrue(all(torch.isfinite(p).all() for p in model.parameters()))


if __name__ == '__main__':
    unittest.main()
