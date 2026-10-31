import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from tactics_code.common import Run, atomic_json, split_for_season


def assert_result_contract(result):
    for row in result if isinstance(result, list) else [result]:
        assert {'method', 'task', 'split', 'is_baseline', 'metrics'} <= row.keys()
        assert type(row['is_baseline']) is bool
        assert all(isinstance(x, (int, float)) and np.isfinite(x) for x in row['metrics'].values())


def test_dashboard_append_merge_finite_atomic(tmp_path):
    args = argparse.Namespace(output=tmp_path, run='fixture', seed=42)
    atomic_json(tmp_path / 'status/ideas.json', {'notes': 'retain me', 'ideas': [{'id': 'existing', 'status': 'proposed'}]})
    for _ in range(2):
        with Run(args, 'test') as run:
            run.metric(split='train', loss=np.float32(.4), invalid=np.inf, epoch=1)
            run.metric(split='val', loss=.2)
            run.result('test', {'finite': 1., 'invalid': np.nan}, details={'unknown': np.nan})
            run.idea('candidate', 'Synthetic check', 'pruned', prune_reason='Synthetic missing support')
    payload = json.loads((tmp_path / 'status/ideas.json').read_text())
    assert payload['notes'] == 'retain me'
    assert {r['id'] for r in payload['ideas']} == {'existing', 'candidate'}
    rows = [json.loads(x) for x in (tmp_path / 'runs/fixture-test/metrics.jsonl').read_text().splitlines()]
    assert [r['step'] for r in rows if r['split'] == 'train'] == [1, 2]
    assert [r['epoch'] for r in rows if r['split'] == 'train'] == [1, 2]
    assert [r['step'] for r in rows if r['split'] == 'val'] == [1, 2]
    assert all('+' in r['time'] or r['time'].endswith('Z') for r in rows)
    result = json.loads((tmp_path / 'results/test.json').read_text())
    assert_result_contract(result)
    assert result['details']['unknown'] is None
    assert not list(tmp_path.rglob('*.tmp'))


def test_unknown_seasons_are_not_training_data():
    assert split_for_season('rlcs-2025') == 'val'
    assert split_for_season('rlcs-2026') == 'test'
    with pytest.raises(ValueError):
        split_for_season('rlcs-2027')


@pytest.mark.parametrize('module', ['audit', 'extract', 'tokens', 'pressure', 'style', 'viz', 'stage'])
def test_cli_help(module):
    completed = subprocess.run([sys.executable, '-m', f'tactics_code.{module}', '--help'], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert all(flag in completed.stdout for flag in ['--seed', '--window', '--fps', '--k'])


def test_figures_render_without_claiming_missing_data(tmp_path, monkeypatch):
    from tactics_code.viz import main
    monkeypatch.setenv('MPLCONFIGDIR', str(tmp_path / 'mpl'))
    main(['--output', str(tmp_path), '--run', 'fixture'])
    for path in (tmp_path / 'figures').glob('*.png'):
        assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
        assert path.stat().st_size > 5000
    assert len(list((tmp_path / 'figures').glob('*.png'))) == 4
    for path in (tmp_path / 'results').glob('*.json'):
        assert_result_contract(json.loads(path.read_text()))
