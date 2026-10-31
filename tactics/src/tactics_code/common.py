"""Dashboard contracts and run bookkeeping, shared by every CLI stage."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import numbers
import os
from pathlib import Path
import re
import tempfile
from typing import Any

DATA_ROOT = (Path.home() / "workspace/rlcs-replays/data")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def clean(value: Any) -> Any:
    """JSON has null, never NaN/Infinity; accept numpy scalars and arrays."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, numbers.Real) and not isinstance(value, (bool, int)):
        return float(value) if math.isfinite(value) else None
    if hasattr(value, 'tolist'):
        return clean(value.tolist())
    if hasattr(value, 'item'):
        return clean(value.item())
    return value


def atomic_json(path: str | Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(clean(obj), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except FileNotFoundError:
        return default


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def split_for_season(season: str) -> str:
    mapping = {'rlcs-21-22': 'train', 'rlcs-2021-22': 'train',
               'rlcs-22-23': 'train', 'rlcs-2022-23': 'train',
               'rlcs-2024': 'train', 'rlcs-2025': 'val', 'rlcs-2026': 'test'}
    if season not in mapping:
        raise ValueError(f'Unknown season {season!r}; declare its split explicitly in code.')
    return mapping[season]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--output', type=Path, default=Path('.'), help='Dashboard tactics/ root')
    parser.add_argument('--run', help='Run prefix; each stage gets its own subdirectory')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--k', type=int, default=8)
    parser.add_argument('--window', type=float, default=6.0)
    parser.add_argument('--fps', type=float, default=10.0)


class Run:
    def __init__(self, args, stage: str, method: str | None = None, is_baseline: bool = False):
        self.args, self.stage = args, stage
        self.output = Path(args.output)
        self.method, self.is_baseline = method or stage, is_baseline
        prefix = getattr(args, 'run', None) or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        self.name = re.sub(r'[^A-Za-z0-9_.-]', '_', f'{prefix}-{stage}')
        self.directory = self.output / 'runs' / self.name
        self.directory.mkdir(parents=True, exist_ok=True)
        self.steps: dict[str, int] = {}
        self.epoch_offsets: dict[str, float] = {}
        self.metrics_path = self.directory / 'metrics.jsonl'
        if self.metrics_path.exists():
            for line in self.metrics_path.read_text().splitlines():
                try:
                    row = json.loads(line)
                    key = row.get('split', 'train')
                    self.steps[key] = max(self.steps.get(key, 0), int(row.get('step', 0)))
                    if isinstance(row.get('epoch'), numbers.Real):
                        self.epoch_offsets[key] = max(self.epoch_offsets.get(key, 0), float(row['epoch']))
                except (ValueError, TypeError, AttributeError):
                    pass
        self.meta = {'name': self.name, 'method': self.method, 'task': stage,
                     'is_baseline': bool(is_baseline), 'status': 'running', 'created': now(),
                     'config': vars(args)}
        atomic_json(self.directory / 'meta.json', self.meta)
        self.log('started')

    def metric(self, split: str = 'train', **values) -> None:
        requested = values.pop('step', None)
        step = self.steps.get(split, 0) + 1
        if requested is not None:
            step = max(step, int(requested))
        self.steps[split] = step
        row = {'step': step, 'time': now(), 'split': split}
        for key, value in values.items():
            if isinstance(value, numbers.Real) and math.isfinite(value):
                row[key] = float(value) + self.epoch_offsets.get(split, 0) if key == 'epoch' else float(value)
        with self.metrics_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
            stream.flush()

    def result(self, name: str, metrics: dict, split: str = 'all', notes: str = '',
               details: Any = None, is_baseline: bool | None = None, **extra) -> dict:
        metrics = {k: float(v) for k, v in metrics.items()
                   if isinstance(v, numbers.Real) and math.isfinite(v)}
        result = {'method': self.method, 'task': self.stage, 'split': split,
                  'is_baseline': self.is_baseline if is_baseline is None else bool(is_baseline),
                  'metrics': metrics, 'notes': notes, 'updated': now()}
        if details is not None:
            result['details'] = details
        result.update(extra)
        atomic_json(self.output / 'results' / (name.removesuffix('.json') + '.json'), result)
        return result

    def idea(self, id: str, name: str, status: str, prune_reason: str = '',
             best_metric: dict | None = None, motivation: str = '') -> None:
        if status not in {'proposed', 'running', 'promising', 'pruned', 'selected'}:
            raise ValueError(f'Invalid idea status: {status}')
        if status == 'pruned' and not prune_reason:
            raise ValueError('A pruned candidate requires its reason')
        path = self.output / 'status' / 'ideas.json'
        with locked(path.with_suffix('.lock')):
            payload = read_json(path, {'ideas': []})
            ideas = payload.setdefault('ideas', [])
            item = next((i for i in ideas if i.get('id') == id), None)
            if item is None:
                item = {'id': id, 'inspiration_refs': []}
                ideas.append(item)
            item.update(name=name, status=status, prune_reason=prune_reason,
                        best_metric=clean(best_metric), motivation=motivation)
            payload['updated'] = now()
            atomic_json(path, payload)

    def log(self, message: str) -> None:
        line = f'{now()} [INFO] {self.stage}: {message}'
        logs = self.output / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f'{self.name}.log').open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')

    def finish(self, status: str = 'done') -> None:
        self.meta.update(status=status, finished=now())
        atomic_json(self.directory / 'meta.json', self.meta)
        if not self.metrics_path.exists():
            self.metric(completed=float(status == 'done'))
        self.log(status)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self.log(f'failed: {exc}')
        self.finish('failed' if exc else 'done')
        return False


def finalize_family(output: str | Path):
    from .stats import update_confirmatory_family
    return update_confirmatory_family(output)
