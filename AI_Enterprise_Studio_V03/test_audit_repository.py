import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import audit_repository as ar


class InventoryTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(['git', *args], cwd=root)

    def test_committed_snapshot_cycles_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, 'init', '-q')
            self.git(repo, 'config', 'user.email', 'fixture@example.invalid')
            self.git(repo, 'config', 'user.name', 'Fixture')
            root = repo / 'V03'
            files = {
                'a.py': 'import b\nimport os\n',
                'b.py': 'def run():\n    import a\n',
                'c.py': 'import d\n',
                'd.py': 'import c\n',
                'pkg/__init__.py': '',
                'pkg/worker.py': 'from . import helper\n',
                'pkg/helper.py': 'import a\n',
                'test_sample.py': 'import a\n',
                'build_sample.py': 'import b\n',
                'broken.py': 'def bad(\n',
                'dynamic.py': 'import importlib\nimportlib.import_module("a")\n',
                'config.json': '{"fixture": "secret-value"}',
                'donnees/secret.py': 'raise AssertionError("never read")\n',
                'credentials/private.pem': 'secret-value',
                'index.html': '<html></html>',
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            (repo / 'outside.py').write_text('import a\n', encoding='utf-8')
            self.git(repo, 'add', '.')
            self.git(repo, 'commit', '-qm', 'fixture')
            (root / 'a.py').write_text('import c\n', encoding='utf-8')
            (root / 'untracked.py').write_text('raise RuntimeError()\n', encoding='utf-8')
            report = ar.audit(root)
            self.assertEqual(report, ar.audit(root))
            self.assertEqual(report['scope'], 'V03/')
            self.assertEqual(report['excluded_private_paths'], 3)
            self.assertEqual(report['runtime_cycles_all_scopes'], [['a', 'b'], ['c', 'd']])
            self.assertEqual(report['runtime_cycles_module_scope'], [['c', 'd']])
            self.assertEqual(report['skipped_python'], [
                {'path': 'broken.py', 'reason': 'parse_error', 'line': 1}])
            edges = {(x['source'], x['target']): x['references'] for x in report['dependencies']}
            self.assertEqual(edges['b', 'a'], [{'scope': 'deferred', 'line': 2}])
            self.assertIn(('pkg.worker', 'pkg.helper'), edges)
            self.assertNotIn(('a', 'c'), edges)
            self.assertEqual(ar.summary(report)['dynamic_import_hint_files'], 1)
            paths = {x['path'] for x in report['files']}
            self.assertFalse(paths & {'config.json', 'donnees/secret.py', 'untracked.py', 'outside.py'})
            self.assertNotIn('secret-value', json.dumps(report))
            self.assertEqual(report['counts']['test'], 1)
            self.assertEqual(report['counts']['tooling'], 1)

    def test_private_path_and_module_resolution(self):
        for path in ('Donnees/x.py', 'pkg/.env.local', 'x/credential.key',
                     'Archives/x.py', 'pkg/config.json', 'a/secret.dpapi'):
            self.assertTrue(ar.private(path), path)
        self.assertFalse(ar.private('interface/original.html'))
        self.assertEqual(ar.module_name('pkg/__init__.py'), 'pkg')
        self.assertIsNone(ar.module_name('not-a-module.py'))
        self.assertEqual(ar.import_targets('pkg.worker', False, '', ('helper',), 1,
                                           {'pkg', 'pkg.helper'}), {'pkg', 'pkg.helper'})
        self.assertEqual(ar.import_targets('pkg.worker', False, '', ('helper',), 2,
                                           {'helper'}), set())

    def test_cycles_exclude_unrelated_nodes_and_self(self):
        self.assertEqual(ar.cyclic_groups({'a', 'b', 'c', 'd'},
                         [('a', 'b'), ('b', 'a'), ('b', 'c'), ('d', 'd')]), [['a', 'b']])


if __name__ == '__main__':
    unittest.main()
