"""Offline regression checks for the Python 3.6 translation filler."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tools import i18n_fill as fill


class FillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.i18n-test-', dir=fill.ROOT)
        self.root = self.tmp.name
        for name in ('tools', 'status', 'results'):
            os.mkdir(os.path.join(self.root, name))
        self.mapping = {'原说明': {'zh': '原说明', 'en': 'Original description'},
                        '原标签': {'zh': '原标签', 'en': 'Original label'},
                        '': {'zh': '', 'en': ''}}
        self.write('tools/i18n_map.json', self.mapping)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.root, name), 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)

    def read(self, name):
        with open(os.path.join(self.root, name), encoding='utf-8') as handle:
            return json.load(handle)

    def run_fill(self, check=False, args=None):
        output, errors = io.StringIO(), io.StringIO()
        argv = ['i18n_fill.py'] + (['--check'] if check else []) + (args or [])
        with patch.object(fill, 'ROOT', self.root), patch.dict(os.environ, {'DASH_DATA_ROOT': self.root, 'DASH_OFFLINE': '1'}), patch('sys.argv', argv), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = fill.main()
        return status, output.getvalue(), errors.getvalue()

    def test_preservation_array_and_idempotence(self):
        original = {'notes': ['原说明', ''], 'name': '原说明', 'effect': -0.037,
                    'ci95': [-0.049, -0.025], 'status': 'failed', 'id': 'untouched'}
        self.write('status/sample.json', original)
        self.assertEqual(self.run_fill()[0], 0)
        result = self.read('status/sample.json')
        for key, value in original.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result['notes_en'], ['Original description', ''])
        path = os.path.join(self.root, 'status/sample.json')
        before = os.stat(path)
        with open(path, 'rb') as handle:
            contents = handle.read()
        self.assertIn('原说明'.encode('utf-8'), contents)
        self.assertIn(b'\n "name"', contents)
        self.assertEqual(self.run_fill()[0], 0)
        self.assertEqual(fill.signature(before), fill.signature(os.stat(path)))
        self.assertEqual(self.run_fill(check=True)[0], 0)

    def test_new_prose_is_reported_and_stale_siblings_removed(self):
        self.write('results/new.json', {'notes': '新结论', 'notes_en': 'Old conclusion', 'notes_zh': '旧结论'})
        result = self.run_fill()
        self.assertEqual(result[0], 1)
        self.assertIn('新结论', result[2])
        self.assertIn('results/new.json/notes', result[2])
        self.assertEqual(self.read('results/new.json'), {'notes': '新结论'})

    def test_check_is_read_only(self):
        original = {'name': '原说明'}
        self.write('status/sample.json', original)
        self.assertEqual(self.run_fill(check=True)[0], 1)
        self.assertEqual(self.read('status/sample.json'), original)

    def test_bilingual_only_label_and_unknown_preservation(self):
        self.write('status/cards.json', {'cards': [{'label_zh': '原标签'}, {'label_zh': '未知标签'}]})
        self.assertEqual(self.run_fill()[0], 1)
        cards = self.read('status/cards.json')['cards']
        self.assertEqual(cards[0], {'label_zh': '原标签', 'label_en': 'Original label'})
        self.assertEqual(cards[1], {'label_zh': '未知标签'})

    def test_concurrent_change_aborts_atomic_replace(self):
        self.write('status/sample.json', {'name': '原说明'})
        path = os.path.join(self.root, 'status/sample.json')
        before = os.stat(path)
        self.write('status/sample.json', {'name': '刚更新的新说明，必须保留'})
        with self.assertRaises(RuntimeError):
            fill.atomic_write(path, {'name': 'old'}, before)
        self.assertEqual(self.read('status/sample.json')['name'], '刚更新的新说明，必须保留')
        self.assertEqual(os.listdir(os.path.dirname(path)), ['sample.json'])

    def test_wrong_language_map_is_reported(self):
        self.mapping['原说明']['en'] = 'English 中文'
        self.write('tools/i18n_map.json', self.mapping)
        self.write('status/sample.json', {'name': '原说明'})
        self.assertEqual(self.run_fill()[0], 1)
        self.assertEqual(self.read('status/sample.json'), {'name': '原说明'})

    def test_explicit_data_root_and_includes_preserve_research_bytes(self):
        snapshot = os.path.join(self.root, 'snapshot')
        os.mkdir(snapshot)
        for name in ('status', 'results'):
            os.mkdir(os.path.join(snapshot, name))
        self.write('status/repository.json', {'name': '原说明'})
        self.write('snapshot/status/phases.json', {'name': '原说明'})
        self.write('snapshot/results/dash_full_summary.json', {'label': '原标签'})
        research_path = os.path.join(snapshot, 'results', 'research.json')
        # Deliberate whitespace and numeric spelling make byte preservation
        # stronger than merely checking that parsed numeric values are equal.
        research_bytes = ('{ "label": "原标签", "estimate": 1.0e-3, '
                          '"ci95": [ -1.00, 1.00 ] }\n').encode('utf-8')
        with open(research_path, 'wb') as handle:
            handle.write(research_bytes)
        research_signature = fill.signature(os.stat(research_path))
        args = ['--data-root', snapshot, '--include', 'status/*.json',
                '--include', 'results/dash_*.json']
        status, output, errors = self.run_fill(args=args)
        self.assertEqual(status, 0, errors)
        self.assertIn('2 files updated', output)
        self.assertEqual(self.read('snapshot/status/phases.json')['name_en'], 'Original description')
        self.assertEqual(self.read('snapshot/results/dash_full_summary.json')['label_en'], 'Original label')
        self.assertEqual(self.read('status/repository.json'), {'name': '原说明'})
        with open(research_path, 'rb') as handle:
            self.assertEqual(handle.read(), research_bytes)
        self.assertEqual(fill.signature(os.stat(research_path)), research_signature)
        self.assertEqual(self.run_fill(check=True, args=args)[0], 0)
        self.assertEqual(self.run_fill(args=args)[0], 0)
        with open(research_path, 'rb') as handle:
            self.assertEqual(handle.read(), research_bytes)
        self.assertEqual(fill.signature(os.stat(research_path)), research_signature)

    def test_include_cannot_escape_explicit_data_root(self):
        snapshot = os.path.join(self.root, 'snapshot')
        os.mkdir(snapshot)
        self.write('status/protected.json', {'name': '原说明'})
        with self.assertRaises(SystemExit) as caught:
            self.run_fill(args=['--data-root', snapshot, '--include', '../status/*.json'])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.read('status/protected.json'), {'name': '原说明'})


if __name__ == '__main__':
    unittest.main()
