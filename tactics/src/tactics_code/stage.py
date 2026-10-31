"""Copy needed frame shards and all lightweight metadata to node-local scratch."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from .common import DATA_ROOT, Run, add_common_args, atomic_json
from .data import frame_root, index_paths, load_manifest, raw_path_lookup, read_index
from .extract import select_replays


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument('--data-root', type=Path, default=DATA_ROOT)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--max-replays', type=int, help='Same per-season cap and seed as extract')
    parser.add_argument('--all-frames', action='store_true', help='Include all-mode shards for full audit')
    args = parser.parse_args(argv)
    source, dest = args.data_root.resolve(), args.destination.resolve()
    if dest == source or source in dest.parents or dest in source.parents:
        raise ValueError('Scratch and source must be separate directory trees')
    with Run(args, 'stage', method='Node-local shard staging') as run:
        index = read_index(source)
        manifest, conflicts = load_manifest(source)
        if conflicts:
            raise ValueError('Conflicting manifest series memberships; resolve before staging')
        raw_paths = raw_path_lookup(source)
        selected = select_replays(index, args.max_replays, args.seed, manifest, raw_paths)
        files = set(index_paths(source))
        if args.all_frames:
            files.update(p for p in frame_root(source).rglob('*.parquet') if not p.name.endswith('.index.parquet'))
        else:
            files.update(Path(p) for p in selected['_frame_path'].unique())
        files.update((source / 'manifest').glob('*.jsonl'))
        total = sum(p.stat().st_size for p in files)
        dest.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(dest).free < total * 1.05:
            raise OSError(f'Scratch needs at least {total * 1.05 / 2**30:.1f} GiB for staged input alone')
        copied = 0
        for number, path in enumerate(sorted(files), 1):
            target = dest / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            # A fresh job scratch directory is expected; verify sizes if resumed.
            if not target.exists() or target.stat().st_size != path.stat().st_size:
                temporary = target.with_name(target.name + '.copying')
                shutil.copy2(path, temporary)
                temporary.replace(target)
            copied += path.stat().st_size
            run.metric(files=number, copied_bytes=copied)
        # Persist just the path evidence; no raw replay bytes need copying.
        atomic_json(dest / 'manifest' / 'kaggle_paths.json', raw_paths)
        details = {'source': source, 'destination': dest, 'max_replays_per_season': args.max_replays,
                   'all_frames': args.all_frames, 'selected_by_season': selected.groupby('season').size().to_dict()}
        atomic_json(dest / 'staging.json', details)
        run.result('stage', {'files': len(files), 'bytes': copied, 'selected_replays': len(selected)}, details=details)
        run.idea('p3-staging', 'Node-local data staging', 'selected', motivation='Avoid random GPFS reads during computation')


if __name__ == '__main__':
    main()
