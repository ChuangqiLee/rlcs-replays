"""Orchestrate one isolated P4 job; invoked by slurm/p4_robust.sh on a worker.

A reused compact corpus is immutable. Its NPZ bytes are copied to scratch;
optional smaller per-season samples filter only the scratch parquet metadata.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from .common import atomic_json, now


def configuration():
    def integer(name, default, minimum=1):
        value = int(os.environ.get(name, default))
        if value < minimum:
            raise ValueError(f'{name} must be >= {minimum}')
        return value

    tasks = os.environ.get('TASKS', 'tokens pressure style').replace(',', ' ').split()
    if not tasks or len(set(tasks)) != len(tasks) or set(tasks) - {'tokens', 'pressure', 'style'}:
        raise ValueError('TASKS must be a nonempty subset of tokens pressure style, without duplicates')
    tasks = [task for task in ('tokens', 'pressure', 'style') if task in tasks]
    window = float(os.environ.get('WINDOW', 6))
    fps = float(os.environ.get('FPS', 10))
    late = float(os.environ.get('PRESSURE_LATE_SECONDS', 60))
    margin = integer('PRESSURE_SCORE_MARGIN', 1)
    if window not in (4, 6, 8) or fps not in (5, 10, 15, 30):
        raise ValueError('WINDOW must be 4/6/8 seconds and FPS 5/10/15/30')
    if not math.isfinite(late) or not 0 < late < 180 or margin not in (1, 2):
        raise ValueError('PRESSURE_LATE_SECONDS must be in (0,180); PRESSURE_SCORE_MARGIN must be 1/2')
    evaluate = os.environ.get('EVALUATE_TEST', '0')
    if evaluate not in ('0', '1'):
        raise ValueError('EVALUATE_TEST must be 0 or 1')
    cap = os.environ.get('MAX_REPLAYS', '300').lower()
    cap = None if cap == 'all' else int(cap)
    if cap is not None and cap < 1:
        raise ValueError('MAX_REPLAYS must be positive (per season), or all')
    config = dict(seed=integer('SEED', 42, 0), k=integer('K', 8, 2), window=window, fps=fps,
                  max_replays=cap, nulls=integer('NULLS', 999), bootstrap=integer('BOOTSTRAP', 2000),
                  tasks=tasks, split='test' if evaluate == '1' else 'val',
                  pressure_late_seconds=late, pressure_score_margin=margin,
                  epochs=integer('EPOCHS', 20), workers=integer('WORKERS', 4),
                  device=os.environ.get('DEVICE', 'cuda'),
                  pressure_regression=os.environ.get('PRESSURE_REGRESSION', 'auto'),
                  style_permutations=integer('STYLE_PERMUTATIONS', os.environ.get('NULLS', '999')))
    if config['device'] not in ('cuda', 'cpu', 'auto') or config['pressure_regression'] not in ('auto', 'ols'):
        raise ValueError('Invalid DEVICE or PRESSURE_REGRESSION')
    if 'style' in tasks and 'tokens' not in tasks and not os.environ.get('REUSE_TOKENS'):
        raise ValueError('Style needs TASKS including tokens or REUSE_TOKENS=<compatible artifacts/tokens>')
    return config


def load_object(path):
    with Path(path).open(encoding='utf-8') as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return payload


def compact_manifest(source):
    import pyarrow.parquet as pq

    manifest = load_object(source / 'extraction.json')
    fps = float(manifest.get('options', {}).get('fps', float('nan')))
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(f'Cannot verify FPS from {source}/extraction.json')
    # extraction.json is written last by extract, but archive copies may still be
    # in flight. Check every nonempty declared shard before trusting the cache.
    shards = manifest.get('shards')
    if not isinstance(shards, list) or not shards:
        raise ValueError(f'No completed shard inventory in {source}/extraction.json')
    declared = set()
    for shard in shards:
        if not shard.get('perspectives', 0):
            continue
        original = Path(shard['shard'])
        relative = Path(original.parent.name) / original.name
        declared.add(relative)
        for file in (source / relative, (source / relative).with_suffix('.parquet')):
            if not file.is_file() or file.stat().st_size == 0:
                raise ValueError(f'Incomplete compact archive: {file}')
        # Read only ZIP directory and parquet footer; do not decompress frame arrays.
        with zipfile.ZipFile(source / relative) as archive:
            if not archive.namelist():
                raise ValueError(f'Empty NPZ archive: {relative}')
        if pq.read_metadata((source / relative).with_suffix('.parquet')).num_rows != shard['perspectives']:
            raise ValueError(f'Compact metadata row count differs from manifest: {relative}')
    actual = {p.relative_to(source) for p in source.rglob('*.npz')}
    if not declared or declared != actual:
        raise ValueError('Compact shard inventory differs from extraction.json; wait for a complete archive')
    return manifest, fps


def cohort_metadata(compact, config, subset=False):
    """Inspect small metadata tables, retaining whole known series when capped."""
    import pandas as pd

    paths = sorted(compact.rglob('*.parquet'))
    frames = [pd.read_parquet(path) for path in paths]
    if not frames:
        raise ValueError('Compact metadata is empty')
    all_rows = pd.concat(frames, ignore_index=True)
    required = {'replay_id', 'season', 'series_id', 'fps'}
    if not required <= set(all_rows):
        raise ValueError('Compact metadata lacks replay, season, series, or FPS provenance')
    if all_rows.empty or not (all_rows.fps == config['fps']).all():
        raise ValueError('Compact metadata has empty/mixed/mismatched FPS')
    replays = all_rows.drop_duplicates(['season', 'replay_id']).copy()
    replays['_group'] = replays.series_id.fillna('').astype(str)
    unknown = replays['_group'] == ''
    replays.loc[unknown, '_group'] = 'unknown:' + replays.loc[unknown, 'replay_id'].astype(str)
    selected = set()
    cap = config['max_replays']
    for season, rows in replays.groupby('season', sort=True):
        groups = list(rows.groupby('_group', sort=True))
        groups.sort(key=lambda item: hashlib.sha256(f"{config['seed']}:{item[0]}".encode()).hexdigest())
        count = 0
        for _, group in groups:
            if subset and cap is not None and count + len(group) > cap:
                continue
            selected.update((str(season), str(replay)) for replay in group.replay_id)
            count += len(group)
    if not selected:
        raise ValueError('No complete series fits the requested cap')
    if subset:
        for path, frame in zip(paths, frames):
            mask = [(str(season), str(replay)) in selected for season, replay in zip(frame.season, frame.replay_id)]
            frame.loc[mask].to_parquet(path, index=False)
    counts = {}
    for season, _ in selected:
        counts[season] = counts.get(season, 0) + 1
    digest = hashlib.sha256(json.dumps(sorted(selected), separators=(',', ':')).encode()).hexdigest()
    return dict(cohort_id=digest, selected_by_season=counts,
                selection_policy='Fixed cached corpus; smaller caps select whole known series by seed' if subset
                else 'Raw-index whole-series selection by seed')


def reuse_tokens(source, output, config, compact_info):
    """Copy only analytic token inputs; never deserialize a model checkpoint."""
    source = source.resolve()
    vocabulary = load_object(source / 'vocabulary.json')
    if vocabulary.get('k') != config['k']:
        raise ValueError('REUSE_TOKENS vocabulary K does not match K')
    # Require an isolated P4 run's manifest to verify all upstream parameters and
    # replay cohort. Other caches should be regenerated by TASKS=tokens style.
    metadata = load_object(source.parent.parent / 'variant.json')
    prior = metadata.get('config', {})
    for key in ('seed', 'k', 'window', 'fps', 'split', 'epochs'):
        if prior.get(key) != config[key]:
            raise ValueError(f'REUSE_TOKENS incompatible {key}')
    if metadata.get('status') != 'complete' or any(metadata.get('compact', {}).get(key) != compact_info.get(key)
                for key in ('cohort_id', 'extraction_signature')):
        raise ValueError('REUSE_TOKENS must be a completed P4 run with the identical replay cohort')
    target = output / 'artifacts' / 'tokens'
    target.mkdir()
    for name in ('vocabulary.json', 'windows.parquet'):
        shutil.copy2(source / name, target / name)
    return str(source)


def main():
    if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('P4_OUTPUT'):
        raise SystemExit('Use slurm/p4_robust.sh inside a SLURM allocation')
    root = Path(os.environ['TACT']).resolve()
    output = Path(os.environ['P4_OUTPUT']).resolve()
    scratch = Path(os.environ['P4_SCRATCH']).resolve()
    tmpdir = Path(os.environ['TMPDIR']).resolve()
    if output.parent != root / 'robust' or tmpdir not in scratch.parents:
        raise ValueError('Output must be an immediate robust/ child; scratch must be inside TMPDIR')
    if root == scratch or root in scratch.parents or scratch in root.parents:
        raise ValueError('Scratch must be separate from the repository')
    metadata = dict(schema_version=1, variant=os.environ['P4_VARIANT'],
                    job_id=os.environ['SLURM_JOB_ID'], status='running', started=now())
    manifest_path = output / 'variant.json'
    atomic_json(manifest_path, metadata)
    try:
        config = configuration()
        metadata['config'] = config
        metadata['commands'] = []
        atomic_json(manifest_path, metadata)
        common = ['--output', str(output), '--run', output.name, '--seed', str(config['seed']),
                  '--fps', str(config['fps']), '--window', str(config['window']), '--k', str(config['k'])]

        def run(module, *arguments):
            command = [sys.executable, '-m', 'tactics_code.' + module, *common, *map(str, arguments)]
            metadata['commands'].append(command)
            atomic_json(manifest_path, metadata)
            print(f'{now()} [RUN] {command}', flush=True)
            subprocess.run(command, check=True, cwd=root)

        compact = scratch / 'compact'
        requested = os.environ.get('REUSE_COMPACT')
        source = Path(requested).expanduser().resolve() if requested else None
        reuse = None
        if source is not None:
            if not source.is_dir():
                raise ValueError(f'REUSE_COMPACT does not exist: {source}')
            reuse, source_fps = compact_manifest(source)
            metadata['requested_compact'] = str(source)
        if source is not None and math.isclose(source_fps, config['fps'], abs_tol=1e-9):
            source_cap = reuse.get('max_replays_per_season')
            cap = config['max_replays']
            if source_cap is not None and (cap is None or cap > int(source_cap)):
                raise ValueError('Requested MAX_REPLAYS exceeds cache cap; supply a larger completed cache or unset REUSE_COMPACT')
            needed = sum(path.stat().st_size for path in source.rglob('*') if path.is_file())
            if shutil.disk_usage(scratch).free < needed * 1.05:
                raise OSError('Insufficient TMPDIR space for compact staging')
            shutil.copytree(source, compact)
            compact_manifest(compact)  # also reject a truncated copy on scratch
            info = cohort_metadata(compact, config, subset=True)
            info.update(mode='reused', source=str(source), source_fps=source_fps,
                        source_max_replays_per_season=source_cap,
                        source_sample_seed=reuse.get('robust_provenance', {}).get('sample_seed'))
            # No second durable copy of reused NPZ data: retain source provenance.
        else:
            if source is not None:
                print(f'FPS differs ({source_fps} -> {config["fps"]}); re-extracting raw data', flush=True)
            data = scratch / 'data'
            sample = [] if config['max_replays'] is None else ['--max-replays', str(config['max_replays'])]
            run('stage', '--data-root', os.environ.get('DATA_ROOT', str(root.parent / 'data')),
                '--destination', data, *sample)
            run('extract', '--data-root', data, '--compact', compact, '--workers', config['workers'],
                '--shard-replays', 250, '--state-map', os.environ.get('STATE_MAP', str(root / 'state_map_rlcs.json')), *sample)
            info = cohort_metadata(compact, config)
            info.update(mode='extracted', source=str(output / 'artifacts' / 'compact'), source_fps=config['fps'],
                        source_max_replays_per_season=config['max_replays'], source_sample_seed=config['seed'])
            extraction = load_object(compact / 'extraction.json')
            extraction['robust_provenance'] = dict(sample_seed=config['seed'], cohort_id=info['cohort_id'])
            atomic_json(compact / 'extraction.json', extraction)
            shutil.copytree(compact, output / 'artifacts' / 'compact')
        extraction = load_object(compact / 'extraction.json')
        info['extraction_signature'] = hashlib.sha256(json.dumps(
            {key: extraction.get(key) for key in ('options', 'state_map')}, sort_keys=True
        ).encode()).hexdigest()
        metadata['compact'] = info
        atomic_json(manifest_path, metadata)
        if 'tokens' in config['tasks']:
            evaluation = ['--evaluate-test'] if config['split'] == 'test' else []
            run('tokens', '--input', compact, '--device', config['device'], '--epochs', config['epochs'],
                '--nulls', config['nulls'], '--bootstrap', config['bootstrap'], *evaluation)
        if 'pressure' in config['tasks']:
            run('pressure', '--input', compact, '--split', config['split'], '--bootstrap', config['bootstrap'],
                '--late-threshold', config['pressure_late_seconds'], '--score-margin', config['pressure_score_margin'],
                '--regression', config['pressure_regression'])
        if 'style' in config['tasks']:
            if 'tokens' not in config['tasks']:
                metadata['reused_tokens'] = reuse_tokens(Path(os.environ['REUSE_TOKENS']).expanduser(), output, config, info)
            run('style', '--input', compact, '--tokens', output / 'artifacts' / 'tokens' / 'windows.parquet',
                '--split', config['split'], '--bootstrap', config['bootstrap'], '--permutations', config['style_permutations'])
        metadata.update(status='complete', finished=now())
    except BaseException as exc:
        metadata.update(status='failed', finished=now(), error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        atomic_json(manifest_path, metadata)


if __name__ == '__main__':
    main()
