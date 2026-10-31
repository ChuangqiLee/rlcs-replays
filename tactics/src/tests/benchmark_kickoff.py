"""Reproduce local tests, synthetic inference, and a qualified CPU estimate."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
import unittest
import zipfile

import numpy as np
import pandas as pd

from tactics_code import kickoff as k
from tactics_code.common import atomic_json
from test_kickoff import fixture, synthetic_units


def main():
    root = Path(__file__).resolve().parents[2]
    reference = root.parents[1] / 'data' / 'repo'
    artifacts = root / 'artifacts'
    start = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_kickoff.py')
    with (artifacts/'tests.log').open('w') as stream, redirect_stdout(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    tests = dict(passed=result.wasSuccessful(), tests_run=result.testsRun, failures=len(result.failures),
                 errors=len(result.errors), skipped=len(result.skipped), wall_seconds=time.perf_counter()-start)
    tests['source_sha256'] = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root/'src'/'tactics_code'/'kickoff.py', root/'src'/'tests'/'test_kickoff.py')}
    atomic_json(artifacts/'self_test.json', tests)
    if not result.wasSuccessful():
        raise SystemExit('Synthetic checks failed; see artifacts/tests.log')

    frames, meta, a, goals, summary = fixture()
    repeats = k.BOOTSTRAP // len(frames.columns)
    t0 = time.perf_counter()
    for _ in range(repeats):
        goals, summary = k.build_replay_events(frames, meta, dict(
            state_decoding='per_replay_decoded', goal_detection='frame_state_transitions'))
        starts = k.kickoff_starts(frames, goals, summary)
    event_seconds = (time.perf_counter()-t0)/repeats
    t0 = time.perf_counter()
    for _ in range(repeats):
        rows = k.replay_units(a, meta, starts, goals, summary)
    compact_seconds = (time.perf_counter()-t0)/repeats
    with tempfile.TemporaryDirectory(dir=artifacts) as tmp:
        path = Path(tmp)/'fixture.npz'
        np.savez_compressed(path, **a)
        t0 = time.perf_counter()
        for _ in range(repeats):
            with zipfile.ZipFile(path) as z:
                for key in a:
                    z.read(key+'.npy')
        decompression_seconds = (time.perf_counter()-t0)/repeats

    train, val = synthetic_units('train'), synthetic_units()
    frozen = k.freeze_thresholds(train)
    train.to_parquet(artifacts/'synthetic_train_units.parquet', index=False)
    val.to_parquet(artifacts/'synthetic_val_units.parquet', index=False)
    atomic_json(artifacts/'synthetic_thresholds.json', frozen)
    t0 = time.perf_counter()
    synthetic = k.analyze(val, frozen)
    inference_seconds = time.perf_counter()-t0
    synthetic.update(status='synthetic_self_test_only', sources=dict(
        train=str(artifacts/'synthetic_train_units.parquet'), val=str(artifacts/'synthetic_val_units.parquet')))
    atomic_json(artifacts/'synthetic_inference.json', synthetic)

    extract_path = reference/'results'/'extract.json'
    extract = json.loads(extract_path.read_text())
    shards = [s for s in extract['details']['shards'] if any(
        '/'+season+'/' in s['shard'] for season in k.TRAIN+(k.VAL,))]
    perspectives_per_replay = sum(s['perspectives'] for s in shards)/sum(s['replays'] for s in shards)
    compact_frames = sum(s['frames'] for s in shards)
    source = (reference/'src'/'tactics_code'/'extract.py').read_text()
    native_fps = float(re.search(r"native_fps = float\(row.get\('fps', (\d+)\)\)", source).group(1))
    native_frames = compact_frames/perspectives_per_replay*native_fps/extract['details']['options']['fps']
    event_total = event_seconds*native_frames/len(frames)
    compact_total = compact_seconds*compact_frames/perspectives_per_replay/len(a['time'])
    decompress_total = decompression_seconds*compact_frames/len(a['time'])
    timing = dict(source=str(extract_path), source_sha256=hashlib.sha256(extract_path.read_bytes()).hexdigest(),
        benchmark_repeats=repeats, synthetic_native_frames=len(frames), synthetic_compact_frames=len(a['time']),
        synthetic_replay_event_seconds=event_seconds, synthetic_replay_compact_seconds=compact_seconds,
        synthetic_shard_decompression_seconds=decompression_seconds,
        synthetic_inference_seconds=inference_seconds, synthetic_inference_units=len(val),
        synthetic_inference_series=int(val['series_id'].nunique()), bootstrap_repeats=k.BOOTSTRAP,
        reference_allowed_replays=sum(s['replays'] for s in shards),
        reference_compact_frames=compact_frames, reference_native_frames_estimate=native_frames,
        estimated_event_seconds=event_total, estimated_compact_seconds=compact_total,
        estimated_decompression_seconds=decompress_total,
        estimated_local_cpu_seconds=event_total+compact_total+decompress_total+inference_seconds,
        caveats=['Synthetic frame-linear projection on this Mac; no native or compact replay files present.',
                 'Includes measured fixture decompression but excludes real native Parquet I/O and filesystem contention.',
                 'Real inference design size, kickoff count and AMD CPU throughput are unmeasured.',
                 'Run whole-series pilot to replace this planning estimate; scheduler walltime is a ceiling, not a forecast.'])
    timing['estimated_local_cpu_minutes'] = timing['estimated_local_cpu_seconds']/60
    atomic_json(artifacts/'timing.json', timing)

    # Deliberately no synthetic values in the requested production result path.
    pending = k.analyze(pd.DataFrame(), k.freeze_thresholds(pd.DataFrame()))
    pending.update(status='not_run_missing_replay_inputs',
        n_units=None, n_series=None,
        reason='Local reference snapshot contains summaries and code, but no decoded native replay or compact arrays.',
        data_sources=[str(reference/'docs'/'P6_reviewer_prereg.md'), str(reference/'docs'/'paper_framing.md'),
                      str(reference/'src'/'tactics_code'/'data.py'), str(reference/'src'/'tactics_code'/'extract.py'),
                      str(reference/'src'/'tactics_code'/'events.py')],
        self_test=str(artifacts/'self_test.json'), runtime_estimate=str(artifacts/'timing.json'))
    for item in pending['outcomes'].values():
        item.update(n_observed=None, n_null=None)
    result_path = root/'results'/'p6_kickoff.json'
    if not result_path.exists() or json.loads(result_path.read_text()).get('status') == 'not_run_missing_replay_inputs':
        atomic_json(result_path, pending)
    print(json.dumps(dict(tests=tests, runtime_estimate_minutes=timing['estimated_local_cpu_minutes'])))


if __name__ == '__main__':
    main()
