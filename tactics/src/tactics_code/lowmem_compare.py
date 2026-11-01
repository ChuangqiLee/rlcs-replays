"""Strict artifact equivalence gate for medium original/low-memory runs.

Run directories must use the same input paths and environment.  Only the
explicit runtime metadata keys below are ignored; scientific fields, row order,
bootstrap draw order, missingness and discrete decisions remain checked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import pushup_dr as dr

ATOL, RTOL = 1e-12, 1e-10
IGNORED_RUNTIME_KEYS = frozenset({
    'updated', 'parameters', 'source_provenance', 'source_sha256',
    'timing_seconds', 'timing_seconds_pipeline',
})


class Comparison:
    def __init__(self):
        self.float_values = 0
        self.max_abs_error = 0.
        self.max_relative_error = 0.

    def _numeric_errors(self, reference, candidate):
        reference, candidate = np.asarray(reference), np.asarray(candidate)
        finite = np.isfinite(reference) & np.isfinite(candidate)
        left, right = reference[finite], candidate[finite]
        self.float_values += int(finite.sum())
        if not len(left):
            return
        difference = np.abs(right-left)
        self.max_abs_error = max(self.max_abs_error, float(np.max(difference)))
        with np.errstate(divide='ignore', invalid='ignore'):
            relative = np.divide(difference, np.abs(left),
                                 out=np.zeros_like(difference), where=left != 0)
        relative[(left == 0) & (difference != 0)] = np.inf
        self.max_relative_error = max(self.max_relative_error, float(np.max(relative)))

    def json(self, reference, candidate, path='$', *, exact=False):
        """Recursively compare types, keys and values; never drop scientific fields."""
        if type(reference) is not type(candidate):
            raise AssertionError(f'{path}: types differ ({type(reference).__name__}, '
                                 f'{type(candidate).__name__})')
        if isinstance(reference, dict):
            ignored = frozenset() if exact else IGNORED_RUNTIME_KEYS
            left_keys, right_keys = set(reference)-ignored, set(candidate)-ignored
            if left_keys != right_keys:
                raise AssertionError(f'{path}: keys differ: reference-only '
                                     f'{sorted(left_keys-right_keys)}, candidate-only '
                                     f'{sorted(right_keys-left_keys)}')
            for key in sorted(left_keys):
                # Tolerance must not admit a changed effect direction or a CI
                # endpoint crossing zero, even for numerically tiny effects.
                if key in {'estimate', 'ci95', 'bootstrap_ci95', 'cr1_ci95'}:
                    left, right = reference[key], candidate[key]
                    if left is not None and right is not None:
                        if not np.array_equal(np.sign(np.asarray(left, dtype=float)),
                                              np.sign(np.asarray(right, dtype=float))):
                            raise AssertionError(f'{path}.{key}: effect/interval sign differs')
                self.json(reference[key], candidate[key], f'{path}.{key}', exact=exact)
        elif isinstance(reference, list):
            if len(reference) != len(candidate):
                raise AssertionError(f'{path}: lengths differ')
            for i, (left, right) in enumerate(zip(reference, candidate)):
                self.json(left, right, f'{path}[{i}]', exact=exact)
        elif isinstance(reference, float) and not exact:
            self._numeric_errors(np.array([reference]), np.array([candidate]))
            if not np.isclose(candidate, reference, atol=ATOL, rtol=RTOL, equal_nan=False):
                raise AssertionError(f'{path}: float differs: {reference!r} -> {candidate!r}')
        elif reference != candidate:
            raise AssertionError(f'{path}: value differs: {reference!r} -> {candidate!r}')

    def array(self, reference, candidate, path):
        if reference.shape != candidate.shape or reference.dtype != candidate.dtype:
            raise AssertionError(f'{path}: array shape/dtype differs: '
                                 f'{reference.shape}/{reference.dtype} -> '
                                 f'{candidate.shape}/{candidate.dtype}')
        for name, function in (('NaN', np.isnan), ('+Inf', np.isposinf), ('-Inf', np.isneginf)):
            if not np.array_equal(function(reference), function(candidate)):
                raise AssertionError(f'{path}: {name} mask differs')
        self._numeric_errors(reference, candidate)
        np.testing.assert_allclose(candidate, reference, atol=ATOL, rtol=RTOL,
                                   equal_nan=True, err_msg=path)

    def summary(self):
        return {'atol': ATOL, 'rtol': RTOL,
                'finite_float_values_compared_with_tolerance': self.float_values,
                'max_abs_error': self.max_abs_error,
                'max_relative_error': (self.max_relative_error
                                       if np.isfinite(self.max_relative_error) else 'inf'),
                'relative_error_definition': 'abs(candidate-reference)/abs(reference); '
                                             '0/0=0 and nonzero/0=inf'}


def _read_json(root, filename):
    return json.loads(dr.guard_path(root / filename).read_text())


def compare_artifacts(task, reference, candidate):
    reference = dr.guard_path(reference).resolve()
    candidate = dr.guard_path(candidate).resolve()
    if task not in ('p4', 'p6'):
        raise ValueError('task must be p4 or p6')
    if not reference.is_dir() or not candidate.is_dir():
        raise ValueError('Both artifact inputs must be existing directories')
    if reference == candidate:
        raise ValueError('Reference and candidate must be distinct directories')
    comparison, files = Comparison(), []
    result_name = 'pushup_possession.json' if task == 'p4' else 'boost_mediation.json'
    comparison.json(_read_json(reference, result_name), _read_json(candidate, result_name), result_name)
    files.append(result_name)
    comparison.json(_read_json(reference, 'selected_replays.json'),
                    _read_json(candidate, 'selected_replays.json'), 'selected_replays.json', exact=True)
    files.append('selected_replays.json')
    tables = ['anchors.parquet', 'goal_events.parquet', 'replay_events.parquet']
    if task == 'p4':
        tables.append('prediction_rows.parquet')
    for filename in tables:
        left = pd.read_parquet(dr.guard_path(reference / filename))
        right = pd.read_parquet(dr.guard_path(candidate / filename))
        pd.testing.assert_frame_equal(left, right, check_exact=True, obj=filename)
        files.append(filename)
    if task == 'p4':
        filename = 'nuisance_predictions.npz'
        with np.load(dr.guard_path(reference / filename), allow_pickle=False) as left, \
                np.load(dr.guard_path(candidate / filename), allow_pickle=False) as right:
            if set(left.files) != {'predictions'} or set(right.files) != {'predictions'}:
                raise AssertionError(f'{filename}: unexpected archive arrays')
            comparison.array(left['predictions'], right['predictions'], filename + ':predictions')
    else:
        filename = 'bootstrap_draws.npy'
        left = np.load(dr.guard_path(reference / filename), mmap_mode='r', allow_pickle=False)
        right = np.load(dr.guard_path(candidate / filename), mmap_mode='r', allow_pickle=False)
        comparison.array(left, right, filename)
    files.append(filename)
    return {'status': 'pass', 'task': task, 'reference': str(reference), 'candidate': str(candidate),
            'files_compared': files, 'ignored_runtime_keys': sorted(IGNORED_RUNTIME_KEYS),
            **comparison.summary()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', choices=('p4', 'p6'), required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    # Validate destinations before any write; a report cannot replace any input
    # or hide among the artifacts it purports to verify.
    reference, candidate = (dr.guard_path(path).resolve()
                            for path in (args.reference, args.candidate))
    output = dr.guard_path(args.out).resolve() if args.out is not None else None
    if output is not None:
        if any(output == root or root in output.parents for root in (reference, candidate)):
            parser.error('--out must be outside both input artifact directories')
        if output.exists():
            parser.error('--out must not overwrite an existing file')
    try:
        report = compare_artifacts(args.task, reference, candidate)
    except (AssertionError, ValueError, OSError, KeyError) as exc:
        report = {'status': 'fail', 'task': args.task, 'error': str(exc),
                  'atol': ATOL, 'rtol': RTOL}
    if output is not None:
        dr.atomic_json(output, report)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
