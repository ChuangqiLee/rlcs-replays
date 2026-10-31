#!/usr/bin/env python3
"""Local Slurm orchestration only; no changes to tactics_code or analysis stages."""
from __future__ import annotations

import argparse
import copy
import getpass
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

HOME_MIN_BYTES = 80 * 1000**3  # requested decimal GB floor
SCRATCH_FIXED_RESERVE = 8 * 1024**3


def quota_report_headroom(report, filesystem, mountpoint):
    """Linux quota -w -v (NOT -s): block values are KiB; join wrapped rows."""
    tokens = report.split()
    for number, token in enumerate(tokens):
        if token not in {filesystem, mountpoint}:
            continue
        fields = tokens[number + 1:number + 4]
        if len(fields) != 3 or not all(re.fullmatch(r'\d+\*?', x) for x in fields):
            raise ValueError('Unrecognized quota block columns')
        used, soft, hard = (int(x.rstrip('*')) * 1024 for x in fields)
        limits = [limit for limit in (soft, hard) if limit > 0]
        return max(0, min(limits) - used) if limits else None
    raise ValueError('quota report has no matching HOME filesystem row')


def home_preflight(home):
    free = shutil.disk_usage(home).free
    if free < HOME_MIN_BYTES:
        raise RuntimeError(f'HOME filesystem has {free} bytes free; need at least {HOME_MIN_BYTES} (80 GB)')
    supplied = os.environ.get('P3X_HOME_QUOTA_FREE_BYTES')
    if supplied is not None:
        if not re.fullmatch(r'\d+', supplied):
            raise ValueError('P3X_HOME_QUOTA_FREE_BYTES must be remaining quota in integer bytes')
        headroom = int(supplied)
        evidence = 'operator-supplied P3X_HOME_QUOTA_FREE_BYTES; use minimum of all applicable quotas'
        report = None
    else:
        try:
            # -l restricts quota reporting to local filesystems (no RPC query).
            report = subprocess.run(['quota', '-l', '-w', '-v', '-u', getpass.getuser()],
                                    text=True, capture_output=True, timeout=30, check=False)
            if report.returncode not in (0, 1) or not report.stdout.strip():
                raise ValueError(report.stderr.strip() or 'quota returned no report')
            df = subprocess.check_output(['df', '-Pk', str(home)], text=True).splitlines()[-1].split()
            headroom = quota_report_headroom(report.stdout, df[0], df[-1])
            report = report.stdout
            evidence = 'quota -l -w -v -u (HOME filesystem row, minimum positive soft/hard limit)'
            # Do not interpret a missing/zero user quota as proof of unrestricted
            # project/group allocation on a shared research filesystem.
            if headroom is None:
                raise ValueError('No finite user quota; site/project headroom must be supplied')
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise RuntimeError('Cannot establish HOME quota headroom. Supply a fresh '
                               'P3X_HOME_QUOTA_FREE_BYTES value from the site quota report '
                               '(minimum remaining user/group/project allowance). df alone is insufficient. '
                               f'Detail: {exc}') from exc
    if headroom < HOME_MIN_BYTES:
        raise RuntimeError(f'HOME quota has {headroom} bytes remaining; need at least {HOME_MIN_BYTES} (80 GB)')
    print(f'[PREFLIGHT] HOME filesystem free={free} bytes; quota remaining={headroom} bytes', flush=True)
    return dict(filesystem_free_bytes=free, quota_remaining_bytes=headroom,
                required_bytes=HOME_MIN_BYTES, quota_evidence=evidence, quota_report=report)


def inventory(source):
    from tactics_code.data import frame_root, index_paths, read_index, load_manifest, raw_path_lookup
    from tactics_code.extract import select_replays
    from tactics_code.common import split_for_season

    index = read_index(source)
    if index['replay_id'].duplicated().any():
        raise ValueError('Duplicate replay IDs across source indexes; resolve before full extraction')
    manifest, conflicts = load_manifest(source)
    if conflicts:
        raise ValueError('Conflicting manifest memberships; resolve before staging')
    raw_paths = raw_path_lookup(source)
    selected = select_replays(index, None, 42, manifest, raw_paths)
    seasons = sorted(index['season'].unique())
    for season in seasons:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', season):
            raise ValueError(f'Unsafe season directory: {season!r}')
        split_for_season(season)  # use the installed split mapping, including test
    indices = index_paths(source)
    frames = sorted(p for p in frame_root(source).rglob('*.parquet')
                    if not p.name.endswith('.index.parquet'))
    manifests = sorted((source / 'manifest').glob('*.jsonl'))
    ownership = {p: set() for p in frames}
    for path, group in index.groupby('_frame_path'):
        path = Path(path)
        if path not in ownership:
            if (group['status'] == 'ok').any():
                raise FileNotFoundError(f'Parsed index rows reference missing frame shard: {path}')
            continue
        ownership[path].update(group['season'].unique())
    # Preserve --all-frames even for unindexed frame files. Infer only from an
    # exact known season path component; otherwise fail season mode explicitly.
    unassigned = []
    for path, owners in ownership.items():
        if not owners:
            owners.update(set(path.relative_to(source).parts) & set(seasons))
            if len(owners) != 1:
                unassigned.append(str(path))
    file_bytes = {p: p.stat().st_size for p in set(indices + frames + manifests)}
    selected_counts = {str(k): int(v) for k, v in selected.groupby('season').size().items()}
    plan = dict(source=str(source), seasons=seasons, indexed_replays=len(index),
                parsed_replays=int((index['status'] == 'ok').sum()),
                eligible_replays=len(selected), selected_by_season=selected_counts,
                all_frame_files=len(frames), full_stage_bytes=sum(file_bytes.values()),
                unassigned_frames=unassigned, units={})
    for season in seasons:
        season_index_paths = [Path(p) for p in index.loc[index['season'] == season, '_index_path'].unique()]
        season_frames = [p for p in frames if season in ownership[p]]
        # Original index sizes are a conservative planning estimate; the exact
        # filtered-view byte total is measured again before calling stage.py.
        plan['units'][season] = dict(
            estimated_stage_bytes=sum(file_bytes[p] for p in set(season_index_paths + season_frames + manifests)),
            frame_files=len(season_frames),
            parsed_replays=int(((index['season'] == season) & (index['status'] == 'ok')).sum()))
    return plan, index, ownership, manifests, raw_paths


def scratch_required(stage_bytes, extra_bytes=0):
    # stage.py itself requires 1.05 * input bytes. Additional allowance is for
    # local compact shards, temporary compressed writes, and small source views.
    default_reserve = max(SCRATCH_FIXED_RESERVE, math.ceil(stage_bytes / 4))
    reserve = int(os.environ.get('P3X_SCRATCH_RESERVE_BYTES', default_reserve))
    if reserve < 0:
        raise ValueError('P3X_SCRATCH_RESERVE_BYTES cannot be negative')
    return math.ceil(stage_bytes * 1.05) + reserve + extra_bytes


def require_scratch(path, needed):
    free = shutil.disk_usage(path).free
    print(f'[PREFLIGHT] scratch free={free} required={needed} bytes at {path}', flush=True)
    if free < needed:
        raise RuntimeError(f'Insufficient node-local scratch: need {needed} bytes, have {free}. '
                           'Use P3X_STAGE_MODE=season for full mode; if a season cannot fit, '
                           'request larger node-local scratch. No partial corpus will be published.')


def make_view(source, view, season, index, ownership, manifests, raw_paths):
    from tactics_code.common import atomic_json
    view.mkdir(parents=True)
    for path, rows in index[index['season'] == season].groupby('_index_path', sort=True):
        target = view / Path(path).relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows.drop(columns=['_index_path', '_frame_path']).to_parquet(target, index=False)
    for path, owners in ownership.items():
        if season in owners:
            target = view / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(path)
    for path in manifests:
        target = view / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(path)
    # stage.py reads this mapping, then writes it into the staged destination.
    # Linking manifest/*.jsonl alone would lose Kaggle-derived series evidence.
    atomic_json(view / 'manifest' / 'kaggle_paths.json', raw_paths)
    return sum(p.stat().st_size for p in view.rglob('*') if p.is_file())


def run_stage(name, common, arguments):
    command = [sys.executable, '-m', f'tactics_code.{name}', *common, *map(str, arguments)]
    print('+ ' + shlex.join(command), flush=True)
    subprocess.run(command, check=True)


def validate_inventory(root, payload):
    """Mirror robust.compact_manifest without loading arrays or analysis code."""
    import pyarrow.parquet as pq
    if not math.isfinite(float(payload['options']['fps'])) or payload['options']['fps'] <= 0:
        raise ValueError('Missing/invalid extraction FPS')
    declared = set()
    all_declared = set()
    for shard in payload['shards']:
        original = Path(shard['shard'])
        relative = Path(original.parent.name) / original.name
        if relative in all_declared:
            raise ValueError(f'Duplicate shard in merged manifest: {relative}')
        all_declared.add(relative)
        if not shard['perspectives']:
            continue
        declared.add(relative)
        array, table = root / relative, (root / relative).with_suffix('.parquet')
        for path in (array, table):
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f'Incomplete compact shard: {path}')
        with zipfile.ZipFile(array) as archive:
            if not archive.namelist():
                raise ValueError(f'Empty compact archive: {array}')
        if pq.read_metadata(table).num_rows != shard['perspectives']:
            raise ValueError(f'Parquet perspective count mismatch: {table}')
    actual = {p.relative_to(root) for p in root.rglob('*.npz')}
    tables = {p.relative_to(root).with_suffix('.npz') for p in root.rglob('*.parquet')}
    if not declared or declared != actual or declared != tables:
        raise ValueError('Compact inventory mismatch or no nonempty shards')


def merge_manifests(payloads, expected, final):
    merged = copy.deepcopy(payloads[0])
    merged['shards'], merged['selected_by_season'] = [], {}
    for payload in payloads:
        for key in ('state_map', 'options', 'max_replays_per_season', 'limitations'):
            if payload[key] != merged[key]:
                raise ValueError(f'Extraction settings differ between units: {key}')
        if payload['max_replays_per_season'] is not None:
            raise ValueError('Full extraction unexpectedly contains a replay cap')
        for season, count in payload['selected_by_season'].items():
            if season in merged['selected_by_season']:
                raise ValueError(f'Season extracted twice: {season}')
            merged['selected_by_season'][season] = count
        for shard in payload['shards']:
            item = copy.deepcopy(shard)
            old = Path(item['shard'])
            item['shard'] = str(final / old.parent.name / old.name)
            merged['shards'].append(item)
    merged['shards'].sort(key=lambda x: x['shard'])
    merged['metrics'] = {key: sum(s[key] for s in merged['shards'])
                         for key in ('replays', 'perspectives', 'frames', 'live_frames')}
    merged['metrics']['shards'] = len(merged['shards'])
    if merged['selected_by_season'] != expected:
        raise ValueError('Merged selected-by-season counts differ from uncapped source inventory')
    if merged['metrics']['replays'] != sum(expected.values()):
        raise ValueError('Merged replay count differs from source eligible replay count')
    return merged


def execute(args):
    # Fail before source inventory/staging, and before creating persistent roots.
    storage = home_preflight(Path.home())
    from tactics_code.common import atomic_json
    source = args.data_root.resolve()
    plan, index, ownership, manifests, raw_paths = inventory(source)
    plan['mode'] = args.mode
    plan['home_preflight'] = storage
    print(json.dumps(plan, indent=2), flush=True)
    if args.mode == 'season' and plan['unassigned_frames']:
        raise ValueError('Cannot safely assign unindexed frame files to seasons: '
                         + repr(plan['unassigned_frames']) + '; use full mode with enough scratch')
    largest = (plan['full_stage_bytes'] if args.mode == 'full' else
               max(unit['estimated_stage_bytes'] for unit in plan['units'].values()))
    raw_map_bytes = len(json.dumps(raw_paths).encode()) * 2
    require_scratch(args.scratch, scratch_required(largest, raw_map_bytes))
    args.output.mkdir(parents=True, exist_ok=False)
    args.artifacts.mkdir(parents=True, exist_ok=False)
    for directory in ('results', 'runs', 'status', 'logs', 'units'):
        (args.output / directory).mkdir()
    state_map = args.output / 'state_map_rlcs.json'
    shutil.copy2(Path(os.environ['TACT']) / 'state_map_rlcs.json', state_map)
    atomic_json(args.output / 'preflight.json', plan)
    # Preserve the exact orchestration code with the isolated run.
    shutil.copy2(Path(__file__), args.output / Path(__file__).name)
    shutil.copy2(Path(__file__).with_name('p3_extract_full.sh'), args.output / 'p3_extract_full.sh')
    incomplete = args.artifacts / '.compact.incomplete'
    incomplete.mkdir()
    final = args.artifacts / 'compact'
    payloads = []
    units = plan['seasons'] if args.mode == 'season' else ['all']
    for unit in units:
        scratch = args.scratch / unit
        scratch.mkdir()
        if args.mode == 'season':
            stage_source = scratch / 'source-view'
            size = make_view(source, stage_source, unit, index, ownership, manifests, raw_paths)
        else:
            stage_source, size = source, plan['full_stage_bytes'] + raw_map_bytes
        require_scratch(scratch, scratch_required(size))
        destination, compact = scratch / 'data', scratch / 'compact'
        common = ['--output', str(args.output), '--run', f'{args.run}-{unit}',
                  '--seed', '42', '--fps', '10', '--window', '6', '--k', '8']
        run_stage('stage', common, ['--data-root', stage_source, '--destination', destination, '--all-frames'])
        run_stage('audit', common, ['--data-root', destination, '--state-map', state_map])
        run_stage('extract', common, ['--data-root', destination, '--compact', compact,
                                     '--workers', '16', '--shard-replays', '250', '--state-map', state_map])
        payload = json.loads((compact / 'extraction.json').read_text())
        # Empty-eligible seasons are legal; only validate nonempty inventories here.
        if any(s['perspectives'] for s in payload['shards']):
            validate_inventory(compact, payload)
        saved = args.output / 'units' / unit
        saved.mkdir()
        shutil.copytree(args.output / 'results', saved / 'results')
        shutil.copy2(compact / 'extraction.json', saved / 'extraction.json')
        shutil.copy2(destination / 'staging.json', saved / 'staging.json')
        for directory in sorted(p for p in compact.iterdir() if p.is_dir()):
            if directory.name not in plan['seasons']:
                raise ValueError(f'Unexpected compact directory: {directory}')
            shutil.copytree(directory, incomplete / directory.name)
        payloads.append(payload)
        # Delete only this job-owned unit after verified local extraction and copy.
        # Copy failures stop before deletion. Final manifest is still absent.
        if any(s['perspectives'] for s in payload['shards']):
            # Validate copied files (inventory for previous units is also present).
            subset = copy.deepcopy(payload)
            for s in subset['shards']:
                if s['perspectives']:
                    relative = Path(s['shard']).parent.name
                    for suffix in ('.npz', '.parquet'):
                        name = Path(s['shard']).with_suffix(suffix).name
                        if (incomplete / relative / name).stat().st_size != (compact / relative / name).stat().st_size:
                            raise ValueError('Copied compact file size mismatch')
        shutil.rmtree(scratch)
    merged = merge_manifests(payloads, plan['selected_by_season'], final)
    validate_inventory(incomplete, merged)
    # Atomic directory rename on the same HOME filesystem, then atomic manifest
    # publication LAST: consumers requiring extraction.json cannot accept partials.
    incomplete.rename(final)
    atomic_json(args.output / 'results' / 'extract.json', dict(
        method='Audited compact extraction', task='extract', split='all', is_baseline=False,
        metrics=merged['metrics'], details={k: v for k, v in merged.items() if k != 'metrics'},
        notes='Merged uncapped extraction; per-unit audit/stage results retained under units/.'))
    atomic_json(args.output / 'results' / 'stage_audit_units.json', dict(
        mode=args.mode, units=[str(args.output / 'units' / u) for u in units],
        note='results/stage.json and audit.json describe the last unit; no pooled audit rates are fabricated.'))
    atomic_json(final / 'extraction.json', merged)
    print(f'[DONE] compact={final}; isolated run={args.output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data-root', 'output', 'scratch', 'artifacts'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--mode', choices=('season', 'full'), default='season')
    args = parser.parse_args()
    try:
        execute(args)
    except Exception as exc:
        print(f'[ERROR] {exc}; no completed compact manifest is published for a failed run.', file=sys.stderr)
        raise


if __name__ == '__main__':
    main()
