#!/usr/bin/env python3
"""Fill reviewed bilingual siblings without changing source fields (Python 3.6).

Run from any directory: python3 tools/i18n_fill.py [--check]
Unknown source strings are listed with JSON pointers; exit 1 until reviewed.
The map is exact-source keyed, so changed live prose cannot reuse stale text.
Only standard library; writes are UTF-8, indent=1, atomic per file. A stat
check avoids replacing a live file changed since it was read (retry next run).
"""
import argparse
import glob
import json
import os
import re
import stat
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = set(('name title motivation note notes description label method target caveat value error '
              'conclusion latest prune_reason rule text venue task split unit units section source '
              'field_borrowed hypothesis metric null test confounds screen_criterion novelty visual').split())
# Machine keys, paths, IDs, statuses and metric-map keys remain machine data.
# Status codes are translated in app.js; status/ideas_brainstorm.columns is a
# list of column identifiers, not prose. Schema titles/descriptions are prose;
# schema types and property keys are not.


def slots(value, pointer=''):
    if isinstance(value, list):
        for i, child in enumerate(value):
            for slot in slots(child, pointer + '/' + str(i)):
                yield slot
    elif isinstance(value, dict):
        # Existing cards may have only label_zh/label_en, with no raw label.
        # Use their existing text as the map key; never invent a raw field.
        bases = set(k[:-3] for k in value if k.endswith(('_zh', '_en')))
        for base in sorted(bases & FIELDS):
            if base not in value:
                source_key = base + ('_zh' if value.get(base + '_zh') else '_en')
                source = value.get(source_key)
                if isinstance(source, str) or (isinstance(source, list) and
                        all(isinstance(x, str) for x in source)):
                    yield value, base, source, pointer + '/' + source_key
        for key, child in list(value.items()):
            if key.endswith(('_zh', '_en')):
                continue
            path = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
            if key in FIELDS and (isinstance(child, str) or
                    isinstance(child, list) and all(isinstance(x, str) for x in child)):
                yield value, key, child, path
            elif isinstance(child, (dict, list)):
                for slot in slots(child, path):
                    yield slot


def signature(info):
    return info.st_ino, info.st_size, info.st_mtime_ns


def atomic_write(path, data, before):
    fd, temporary = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(before.st_mode))
        if signature(os.stat(path)) != signature(before):
            raise RuntimeError('file changed during translation; rerun: ' + path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report missing/stale siblings without writing')
    parser.add_argument('--data-root', default=os.environ.get('DASH_DATA_ROOT', ROOT),
                        help='snapshot directory; defaults to DASH_DATA_ROOT or repository root')
    parser.add_argument('--include', action='append',
                        help='relative glob to process; repeat to limit writes to authorized files')
    args = parser.parse_args()
    data_root = os.path.abspath(os.path.expanduser(args.data_root))
    with open(os.path.join(ROOT, 'tools', 'i18n_map.json'), encoding='utf-8') as handle:
        translations = json.load(handle)
    missing, changed, failures = {}, [], []
    paths = set()
    for pattern in args.include or ['status/*.json', 'results/*.json']:
        for path in glob.glob(os.path.join(data_root, pattern)):
            if os.path.commonpath([os.path.realpath(path), os.path.realpath(data_root)]) != os.path.realpath(data_root):
                parser.error('included path is outside data root: ' + path)
            paths.add(path)
    for path in sorted(paths):
        try:
            with open(path, encoding='utf-8') as handle:
                before = os.fstat(handle.fileno())
                data = json.load(handle)
            dirty = False
            for parent, field, original, pointer in slots(data):
                sources = original if isinstance(original, list) else [original]
                complete = True
                for source in sources:
                    entry = translations.get(source)
                    if not isinstance(entry, dict) or not all(isinstance(entry.get(l), str) and (entry[l] or not source) for l in ('zh', 'en')) or re.search(r'[\u3000-\u9fff\uff00-\uffef]', entry.get('en', '')):
                        missing.setdefault(source, []).append(os.path.relpath(path, data_root) + pointer)
                        complete = False
                # Remove stale siblings on unknown changed sources; do not silently
                # serve an old conclusion for a newly updated original sentence.
                for language in ('zh', 'en'):
                    key = field + '_' + language
                    if complete:
                        texts = [translations[s][language] for s in sources]
                        translated = texts if isinstance(original, list) else texts[0]
                        if parent.get(key) != translated:
                            parent[key] = translated
                            dirty = True
                    elif field in parent and key in parent:
                        del parent[key]
                        dirty = True
            if dirty:
                changed.append(os.path.relpath(path, data_root))
                if not args.check:
                    atomic_write(path, data, before)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append('{}: {}'.format(path, exc))
    for source, locations in sorted(missing.items()):
        print('UNTRANSLATED ' + json.dumps({'source': source, 'locations': locations}, ensure_ascii=False), file=sys.stderr)
    for failure in failures:
        print('ERROR ' + failure, file=sys.stderr)
    print('{} files {}; {} untranslated strings; {} errors'.format(
        len(changed), 'need updates' if args.check else 'updated', len(missing), len(failures)))
    return 1 if missing or failures or (args.check and changed) else 0


if __name__ == '__main__':
    sys.exit(main())
