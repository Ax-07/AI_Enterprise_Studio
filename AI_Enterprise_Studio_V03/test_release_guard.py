import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import warnings
import zipfile

import build_candidate
import prepare_update
import release_metadata
import release_paths
import smoke_release_guard as guard


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = self.base/'repo'
        self.repo.mkdir()
        self.root = self.repo/'V03'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        files = {name: b'fixture' for name in release_paths.REQUIRED}
        files.update({'serveur.py': b'VERSION="3.0.0"\n', 'core/registry.py': b'public',
                      'config.json': b'PRIVATE', 'release_version.json': json.dumps({
                          'schema': release_metadata.SCHEMA, 'engine_version': '3.0.0',
                          'release_version': '3.1.0', 'phase': 'R02.4',
                          'status': 'candidate'}).encode()})
        for name, data in files.items():
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.baseline = self.base/'baseline.json'
        self.baseline.write_text(json.dumps({'schema': guard.BASELINE_SCHEMA,
                                             'commit': self.commit,
                                             'paths': ['serveur.py', 'core/registry.py']}))
        self.archive = self.base/'release.zip'
        build_candidate.build(self.archive, self.root)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo)

    def verify(self, archive=None):
        return guard.verify_archive(archive or self.archive, self.root, self.baseline)

    def altered(self, change):
        dest = self.base/'altered.zip'
        with zipfile.ZipFile(self.archive) as old, zipfile.ZipFile(dest, 'w') as new:
            for name in old.namelist():
                data = change(name, old.read(name))
                if data is not None:
                    new.writestr(name, data)
        return dest

    def test_archive_and_prepared_copy(self):
        report = self.verify()
        self.assertEqual(report['commit'], self.commit)
        self.assertEqual(report['historical_paths'], 2)
        self.assertNotIn('config.json', report['files'])
        unpacked = self.base/'unpacked'
        with zipfile.ZipFile(self.archive) as z:
            z.extractall(unpacked)
        target = self.base/'target'
        target.mkdir()
        prepare_update.copy_runtime(unpacked/guard.PREFIX, target)
        (target/'config.json').write_bytes(b'PRIVATE CONFIG')
        (target/'donnees').mkdir()
        (target/'donnees/enterprise.sqlite3').write_bytes(b'PRIVATE DATABASE')
        guard.verify_installation(target, report)
        (target/'core/registry.py').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            guard.verify_installation(target, report)

    def test_archive_rejects_missing_or_altered_file(self):
        for replacement in (None, b'corrupt'):
            with self.subTest(replacement=replacement):
                dest = self.altered(lambda name, data: replacement
                                    if name.endswith('/core/registry.py') else data)
                with self.assertRaises(ValueError):
                    self.verify(dest)

    def test_archive_rejects_extra_and_duplicate_entries(self):
        for name in ('config.json', 'serveur.py'):
            with self.subTest(name=name):
                dest = self.altered(lambda name, data: data)
                with warnings.catch_warnings(), zipfile.ZipFile(dest, 'a') as z:
                    warnings.simplefilter('ignore', UserWarning)
                    z.writestr(guard.PREFIX+name, b'unexpected')
                with self.assertRaises(ValueError):
                    self.verify(dest)

    def test_archive_rejects_wrong_commit_metadata(self):
        def change(name, data):
            if name.endswith('/BUILD_INFO.json'):
                value = json.loads(data)
                value['commit'] = '0'*40
                return json.dumps(value).encode()
            return data
        with self.assertRaises(ValueError):
            self.verify(self.altered(change))

    def test_historical_path_missing_from_new_commit(self):
        self.git('rm', 'V03/core/registry.py')
        self.git('commit', '-qm', 'remove historical file')
        build_candidate.build(self.archive, self.root)
        with self.assertRaisesRegex(ValueError, 'Historical runtime paths missing'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
