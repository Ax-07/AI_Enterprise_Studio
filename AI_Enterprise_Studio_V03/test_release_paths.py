from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
import zipfile

import build_candidate
import prepare_update
import release_paths as p


class ReleasePathsTests(unittest.TestCase):
    def fixture(self, root):
        files = {name: b'fixture' for name in p.REQUIRED}
        files.update({
            'serveur.py': b'VERSION="3.0.0"\n',
            'release_version.json': "{\"schema\":\"aes.release.version.v1\",\"engine_version\":\"3.0.0\",\"release_version\":\"3.1.0\",\"phase\":\"R02.3\",\"status\":\"candidate\"}".encode('utf-8'),
            'core/agents/__init__.py': b'',
            'core/agents/registry.py': b'public-source',
            'departments/nexus/service.py': b'public-service',
            'interface/assets/room.webp': b'public-asset',
            'n8n/compose.yaml': b'public-config',
            'sandbox/Dockerfile': b'FROM scratch',
            'docs/architecture.md': b'doc',
            'INSTALLATION.txt': b'instructions',
            'config.json': b'PRIVATE',
            'config.example.json': b'not included in R02.2',
            'donnees/enterprise.sqlite3': b'PRIVATE',
            'core/agents/.env': b'PRIVATE',
            'core/agents/test_registry.py': b'test',
            'core/agents/secrets/key.py': b'PRIVATE',
            'interface/assets/secret.key': b'PRIVATE',
            'interface/unknown.bin': b'PRIVATE',
            'n8n/credentials.json': b'PRIVATE',
            'archives/old.py': b'PRIVATE',
        })
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return files

    def git(self, root, *args):
        return subprocess.check_output(['git', *args], cwd=root)

    def test_build_and_copy_agree_on_committed_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / 'repo'
            repo.mkdir()
            root = repo / 'V03'
            root.mkdir()
            files = self.fixture(root)
            self.git(repo, 'init', '-q')
            self.git(repo, 'config', 'user.email', 'fixture@example.invalid')
            self.git(repo, 'config', 'user.name', 'Fixture')
            self.git(repo, 'add', '.')
            self.git(repo, 'commit', '-qm', 'fixture')
            sha = self.git(repo, 'rev-parse', 'HEAD').decode().strip()
            (root/'release_version.json').write_bytes(b'INVALID LOCAL VERSION')
            (root/'core/agents/registry.py').write_bytes(b'UNCOMMITTED')
            (root/'core/agents/extra.py').write_bytes(b'UNTRACKED')
            dest = base/'release.zip'
            build_candidate.build(dest, root)
            unpacked = base/'unpacked'
            with zipfile.ZipFile(dest) as z:
                z.extractall(unpacked)
            candidate = unpacked/'AI_Enterprise_Studio_V03'
            target = base/'target'
            target.mkdir()
            prepare_update.copy_runtime(candidate,target)
            actual = {x.relative_to(target).as_posix(): x.read_bytes()
                      for x in target.rglob('*') if x.is_file()}
            expected = {k: v for k, v in files.items() if p.allowed(k)}
            meta = json.loads(actual.pop('BUILD_INFO.json'))
            self.assertEqual(meta['commit'], sha)
            self.assertFalse(meta['contains_local_data'])
            self.assertEqual(meta['release_version'], '3.1.0')
            self.assertEqual(meta['engine_version'], '3.0.0')
            self.assertEqual(meta['status'], 'candidate')
            self.assertEqual(actual, expected)
            self.assertFalse(any(b'PRIVATE' in data for data in actual.values()))

    def test_directory_copy_uses_same_policy(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base/'source'
            source.mkdir()
            files = self.fixture(source)
            target = base/'target'
            target.mkdir()
            prepare_update.copy_runtime(source,target)
            self.assertEqual({x.relative_to(target).as_posix()
                              for x in target.rglob('*') if x.is_file()},
                             {k for k in files if p.allowed(k)})

    def test_invalid_paths_and_missing_requirements(self):
        for name in ('../serveur.py','/serveur.py','core//a.py','core/../a.py',
                     'C:/serveur.py','core/a\\b.py','core/NUL.py','core/a.py '):
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.allowed(name)
        with self.assertRaises(ValueError):
            p.checked_names(['serveur.py'])
        with self.assertRaises(ValueError):
            p.checked_names(list(p.REQUIRED)+['core/A.py','core/a.py'])

    def test_private_and_unapproved_paths(self):
        for name in ('core/credentials/key.py','core/.env.py','core/config.json',
                     'core/a.sqlite3','core/tests/test_a.py','interface/file.p12',
                     'n8n/.git/config','n8n/secrets.json','elsewhere/service.py',
                     'interface/a.bin','BUILD_INFO.json'):
            self.assertFalse(p.allowed(name), name)
        self.assertTrue(p.allowed('BUILD_INFO.json',metadata=True))
        self.assertTrue(p.allowed('core/nested/__init__.py'))

    def test_selected_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            link = root/'core/agents/link.py'
            try:
                os.symlink(root/'config.json',link)
            except (OSError,NotImplementedError):
                self.skipTest('Symlink creation unavailable')
            with self.assertRaises(ValueError):
                p.runtime_files(root)


if __name__ == '__main__':
    unittest.main()
