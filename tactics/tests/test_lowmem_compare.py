"""The comparison gate is tested entirely with temporary synthetic artifacts."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from tactics_code import lowmem_compare as compare


def write_fixture(root, task):
    root.mkdir()
    result = {'estimate': .125, 'rules': {'R4': {'pass': True}}, 'rows': 2,
              'details': {'threshold': 500., 'timing_seconds': {'total': 3.}},
              'parameters': {'workers': 32}, 'updated': 'old', 'source_sha256': {'module': 'a'}}
    filename = 'pushup_possession.json' if task == 'p4' else 'boost_mediation.json'
    (root / filename).write_text(json.dumps(result))
    (root / 'selected_replays.json').write_text(json.dumps(['a', 'b']))
    table = pd.DataFrame({'replay_id': ['a', 'b'], 'value': [1.5, 2.5]})
    names = ['anchors.parquet', 'goal_events.parquet', 'replay_events.parquet']
    if task == 'p4':
        names.append('prediction_rows.parquet')
    for name in names:
        table.to_parquet(root / name, index=False)
    values = np.array([[.1, np.nan, np.inf, -np.inf], [.4, .5, .6, .7]])
    if task == 'p4':
        np.savez_compressed(root / 'nuisance_predictions.npz', predictions=values)
    else:
        np.save(root / 'bootstrap_draws.npy', values, allow_pickle=False)


class ComparisonTests(unittest.TestCase):
    def test_json_metadata_only_ignored(self):
        reference = {'estimate': .25, 'count': 8, 'pass': True,
                     'details': {'timing_seconds': {'total': 1}, 'threshold': .05}}
        candidate = {'estimate': .25 + 1e-12, 'count': 8, 'pass': True,
                     'details': {'timing_seconds': {'total': 100}, 'threshold': .05},
                     'parameters': {'lowmem': True}}
        compare.Comparison().json(reference, candidate)
        for key, value in (('count', 9), ('pass', False), ('estimate', .250001), ('count', 8.)):
            wrong = dict(candidate, **{key: value})
            with self.assertRaises(AssertionError):
                compare.Comparison().json(reference, wrong)
        candidate['details']['threshold'] = .06
        with self.assertRaises(AssertionError):
            compare.Comparison().json(reference, candidate)
        for key, left, right in (('estimate', 1e-13, -1e-13),
                                  ('ci95', [-1e-13, 1.], [1e-13, 1.])):
            with self.assertRaises(AssertionError):
                compare.Comparison().json({key: left}, {key: right})

    def test_tolerance_and_missingness(self):
        reference = np.array([.5, 0., np.nan, np.inf, -np.inf])
        for candidate in (np.array([.5+1e-7, 0., np.nan, np.inf, -np.inf]),
                          np.array([.5, 0., 0., np.inf, -np.inf]),
                          np.array([.5, 0., np.nan, -np.inf, -np.inf])):
            with self.assertRaises(AssertionError):
                compare.Comparison().array(reference, candidate, 'draws')
        candidate = reference.copy()
        candidate[0] += 1e-12
        stats = compare.Comparison()
        stats.array(reference, candidate, 'draws')
        self.assertGreater(stats.summary()['max_abs_error'], 0)

    def test_end_to_end_and_exact_parquet(self):
        for task in ('p4', 'p6'):
            with self.subTest(task=task), tempfile.TemporaryDirectory(prefix='lowmem-compare-') as tmp:
                root = Path(tmp)
                reference, candidate = root / 'reference', root / 'candidate'
                write_fixture(reference, task)
                write_fixture(candidate, task)
                self.assertEqual(compare.compare_artifacts(task, reference, candidate)['status'], 'pass')
                filename = candidate / 'anchors.parquet'
                table = pd.read_parquet(filename)
                table.loc[0, 'value'] += 1e-14
                table.to_parquet(filename, index=False)
                with self.assertRaises(AssertionError):
                    compare.compare_artifacts(task, reference, candidate)

    def test_cli_exit_and_report_destination(self):
        with tempfile.TemporaryDirectory(prefix='lowmem-compare-') as tmp:
            root = Path(tmp)
            reference, candidate = root / 'reference', root / 'candidate'
            write_fixture(reference, 'p6')
            write_fixture(candidate, 'p6')
            args = ['--task', 'p6', '--reference', str(reference), '--candidate', str(candidate)]
            report = root / 'report.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(args + ['--out', str(report)]), 0)
            self.assertEqual(json.loads(report.read_text())['status'], 'pass')
            (candidate / 'selected_replays.json').write_text('["b", "a"]')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(args), 1)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                compare.main(args + ['--out', str(candidate / 'report.json')])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                compare.main(args + ['--out', str(report)])


if __name__ == '__main__':
    unittest.main()
