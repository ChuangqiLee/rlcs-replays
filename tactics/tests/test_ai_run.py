"""Synthetic runner contract tests: no real input data or GPU required."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_experiments import run


class RunnerTests(unittest.TestCase):
    def test_list_jobs_is_fixed_and_needs_no_tensor_imports(self):
        import builtins
        original = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'numpy', 'pandas'):
                raise AssertionError('Job listing must not import training dependencies')
            return original(name, *args, **kwargs)
        output = io.StringIO()
        with patch('builtins.__import__', guarded_import), contextlib.redirect_stdout(output):
            run.main(['--list-jobs'])
        jobs = json.loads(output.getvalue())
        self.assertEqual(len(jobs), 60)
        self.assertEqual([item['index'] for item in jobs], list(range(60)))
        self.assertEqual({item['seed'] for item in jobs}, {42, 43, 44})
        self.assertEqual(len({item['name'] for item in jobs}), 20)

    def test_invalid_index_and_production_without_slurm_fail_before_inputs(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main(['--job-index', '60'])
            with self.assertRaises(SystemExit):
                run.main(['--job-index', '0', '--compact', '/never/opened'])
            with self.assertRaises(SystemExit):
                run.main(['--smoke', '--compact', '/never/opened',
                          '--out-dir', '/never/opened', '--scratch', '/never/opened'])

    def test_environment_time_counts_toward_budget_and_failure_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='ai-run-', dir='/tmp') as directory:
            root = Path(directory).resolve()
            output = root/'output'
            env = dict(TMPDIR=str(root), AI_START_EPOCH=str(time.time()-1100))
            with patch.dict(os.environ, env), patch.object(run, 'provenance', return_value={}), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(TimeoutError, 'Environment setup'):
                    run.main(['--smoke', '--device', 'cpu', '--out-dir', str(output),
                              '--scratch', str(root/'scratch')])
            report = json.loads((output/'report.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(report['synthetic'])
            self.assertFalse(report['test_opened'])
            self.assertEqual(report['total_budget_seconds'], 1000)
            self.assertGreater(report['whole_job_seconds'], 1000)

    def test_historical_reference_requires_source_population_and_metric_agreement(self):
        values = dict(top1=.15392254220456802, top5=.3565, mrr=.2621)
        metrics = {key: dict(estimate=value) for key, value in values.items()}
        inputs = [dict(path='/source/rlcs-2025/compact-000.npz', metadata_sha256='synthetic', bytes=123)]
        data = SimpleNamespace(games=[None]*4, report=dict(input_files=inputs, replay_ids=['a', 'b']))
        reference = dict(input_files=inputs, replay_ids=['a', 'b'], player_games=4,
                         eligible_ids=['alice', 'bob'], n_gallery=2,
                         primary=dict(queries_evaluated=3, metrics=metrics))
        evaluation = dict(population=dict(eligible_ids=['alice', 'bob'], n_gallery=2),
                          primary=dict(queries_evaluated=3,
                                       methods=dict(handcrafted=dict(metrics=metrics))))
        with tempfile.TemporaryDirectory(prefix='ai-reference-') as directory:
            path = Path(directory)/'reference.json'
            path.write_text(json.dumps(reference))
            match = run.reference_check(evaluation, data, path)
            self.assertTrue(match['matched'], match)
            evaluation['primary']['queries_evaluated'] = 2
            mismatch = run.reference_check(evaluation, data, path)
            self.assertFalse(mismatch['matched'])
            self.assertFalse(mismatch['checks']['queries'])
            self.assertFalse(run.reference_check(evaluation, data, None)['matched'])


if __name__ == '__main__':
    unittest.main()
