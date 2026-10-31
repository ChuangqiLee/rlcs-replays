"""Actual Parquet end-to-end smoke. Requires pyarrow, never contacts a cluster."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from tests.synthetic import make_rlcs_replay, write_fixture
from tests.test_dashboard import assert_result_contract


def test_parquet_pipeline(tmp_path):
    pytest.importorskip('pyarrow', reason='Actual parquet integration requires the declared pyarrow dependency')
    from tactics_code.data import iter_compact
    root = write_fixture(tmp_path / 'data', series=4, games=2, seconds=40)
    output = tmp_path / 'output'
    common = ['--output', str(output), '--run', 'fixture', '--seed', '42', '--k', '2', '--window', '4', '--fps', '10']
    def run(module, *args):
        result = subprocess.run([sys.executable, '-m', f'tactics_code.{module}', *common, *map(str, args)],
                                capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, f'{module}:\n{result.stdout}\n{result.stderr}'
    run('audit', '--data-root', root, '--state-map', root / 'state-map.synthetic.json')
    run('stage', '--data-root', root, '--destination', tmp_path / 'scratch', '--max-replays', '8')
    run('extract', '--data-root', tmp_path / 'scratch', '--state-map', root / 'state-map.synthetic.json',
        '--compact', output / 'compact', '--workers', '2', '--shard-replays', '4', '--max-replays', '8')
    compact = list(iter_compact(output / 'compact'))
    assert len(compact) == 80  # 5 seasons × 8 eligible games × 2 focal teams
    for meta, arrays in compact:
        assert arrays['ball'].shape == (400, 6)
        assert arrays['players'].shape == (400, 6, 8)
        assert meta['series_id']
        assert np.isfinite(arrays['score_diff']).all()
        assert not arrays['live'][0]
    run('tokens', '--input', output / 'compact', '--device', 'cpu', '--epochs', '1', '--hidden', '8',
        '--batch-size', '32', '--max-windows', '100', '--max-val-windows', '50', '--nulls', '9', '--bootstrap', '19',
        '--min-motif-count', '1')
    run('pressure', '--input', output / 'compact', '--bootstrap', '19', '--regression', 'ols')
    run('style', '--input', output / 'compact', '--min-series', '2', '--min-events', '1', '--permutations', '19', '--bootstrap', '19')
    run('viz')
    windows = pd.read_parquet(output / 'artifacts/tokens/windows.parquet')
    assert {'train', 'val'} == set(windows.split)  # Default never transforms held-out 2026.
    assert windows.groupby('series_id').split.nunique().max() == 1
    assert windows.token.between(0, 1).all()
    for name in ['audit', 'stage', 'extract', 'tokens', 'pressure', 'style', 'viz', 'confirmatory']:
        assert_result_contract(json.loads((output / f'results/{name}.json').read_text()))
    for path in (output / 'runs').glob('*/meta.json'):
        assert json.loads(path.read_text())['status'] == 'done'
    assert len(list((output / 'figures').glob('*.png'))) == 4


def test_default_rlcs_map_extraction_and_audit(tmp_path):
    pytest.importorskip('pyarrow', reason='Default RLCS-map integration requires parquet')
    import pyarrow as pa
    import pyarrow.parquet as pq
    from tactics_code.data import iter_compact

    root = tmp_path / 'data'
    shard = root / 'frames' / 'fps30' / 'rlcs-2024' / 'part-0.parquet'
    shard.parent.mkdir(parents=True)
    frame, row, _ = make_rlcs_replay()
    rows = []
    with pq.ParquetWriter(shard, pa.Table.from_pandas(frame, preserve_index=False).schema) as writer:
        for variant in ('agree', 'mismatch', 'ambiguous'):
            current = frame.copy()
            record = dict(row, replay_id=f'rlcs-{variant}')
            current['replay_id'] = record['replay_id']
            if variant == 'mismatch':
                meta = json.loads(record['replay_meta'])
                meta['team_zero'][0]['stats']['Goals'] += 1
                record['replay_meta'] = json.dumps(meta)
            elif variant == 'ambiguous':
                current.loc[989, 'Ball - position y'] = 0
            writer.write_table(pa.Table.from_pandas(current, preserve_index=False), row_group_size=len(current))
            rows.append(record)
    pd.DataFrame(rows).to_parquet(shard.with_name('part-0.index.parquet'), index=False)
    output = tmp_path / 'output'
    for module, extra in [('audit', []), ('extract', ['--workers', '1'])]:
        # No --state-map or heuristic flag: exercise the checked-in default.
        result = subprocess.run([sys.executable, '-m', f'tactics_code.{module}', '--data-root', str(root),
                                 '--output', str(output), '--run', 'rlcs-default', *extra],
                                capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, f'{module}:\n{result.stdout}\n{result.stderr}'
    audited = json.loads((output / 'results' / 'audit.json').read_text())
    assert audited['metrics']['metadata_timed_goal_coverage'] == 0
    assert audited['metrics']['timed_goal_coverage'] == pytest.approx(2 / 3)
    assert audited['metrics']['goal_agreement_rate'] == pytest.approx(1 / 3)
    details = audited['details']
    assert details['game_state_counts'] == {'73': 1080, '78': 32760, '96': 810}
    assert details['game_state_transitions']['78->96'] == 9
    assert details['game_state_transitions']['78->73'] == 3
    assert details['goals']['ambiguous_goal_events'] == 1
    assert details['goals']['goal_disagreement_replays'] == 2
    compact = list(iter_compact(output / 'compact'))
    assert len(compact) == 6
    for meta, arrays in compact:
        assert meta['state_source'] == 'explicit_state_map'
        assert meta['score_source'] == 'frame_state_transitions'
        assert arrays['live'].any()
        assert (arrays['overtime'] == 1).any()
        if meta['replay_id'] == 'rlcs-ambiguous':
            assert np.isnan(arrays['score_diff'][arrays['frame'] > 990]).all()
        else:
            assert np.isfinite(arrays['score_diff']).all()


def test_rlcs_audit_state_and_goal_report_without_arrow(tmp_path, monkeypatch):
    """Exercise real audit aggregation while replacing only the parquet I/O."""
    from types import ModuleType, SimpleNamespace
    from tactics_code import audit as audit_module

    frame, row, _ = make_rlcs_replay()
    shard = tmp_path / 'part-0.parquet'
    shard.touch()
    frames, rows = {}, []
    for variant in ('agree', 'mismatch', 'ambiguous'):
        current = frame.copy()
        record = dict(row, replay_id=variant, _frame_path=str(shard))
        current['replay_id'] = variant
        if variant == 'mismatch':
            meta = json.loads(record['replay_meta'])
            meta['team_zero'][0]['stats']['Goals'] += 1
            record['replay_meta'] = json.dumps(meta)
        elif variant == 'ambiguous':
            current.loc[989, 'Ball - position y'] = 0
        frames[variant] = current
        rows.append(record)
    arrow = ModuleType('pyarrow')
    parquet = ModuleType('pyarrow.parquet')
    parquet.ParquetFile = lambda path: SimpleNamespace(schema_arrow=SimpleNamespace(names=list(frame.columns)))
    arrow.parquet = parquet
    monkeypatch.setitem(sys.modules, 'pyarrow', arrow)
    monkeypatch.setitem(sys.modules, 'pyarrow.parquet', parquet)
    monkeypatch.setattr(audit_module, 'read_index', lambda root: pd.DataFrame(rows))
    monkeypatch.setattr(audit_module, 'load_manifest', lambda root: ({}, []))
    monkeypatch.setattr(audit_module, 'raw_path_lookup', lambda root: {})
    monkeypatch.setattr(audit_module, 'iter_frame_replays',
                        lambda path, selected, columns: ((rid, frames[rid][columns]) for rid in sorted(selected)))
    metrics, details = audit_module.audit(tmp_path)
    assert metrics['metadata_timed_goal_coverage'] == 0
    assert metrics['timed_goal_coverage'] == pytest.approx(2 / 3)
    assert metrics['goal_agreement_rate'] == pytest.approx(1 / 3)
    assert details['game_state_counts'] == {'73': 1080, '78': 32760, '96': 810}
    assert details['game_state_transitions'] == {'73->78': 12, '78->96': 9, '96->73': 6, '78->73': 3}
    assert details['goals']['frame_goal_events'] == 9
    assert details['goals']['ambiguous_goal_events'] == 1
    assert details['goals']['goal_agreement_comparable_replays'] == 3
    assert details['goals']['goal_agreement_replays'] == 1
    assert details['goals']['goal_disagreement_replays'] == 2
    rendered = audit_module.markdown(metrics, details)
    assert '78->96' in rendered
    assert '33.3%' in rendered
