import json
import unittest
from pathlib import Path
import release_metadata as m


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.version = {'schema': m.SCHEMA, 'engine_version': '3.0.0',
                        'release_version': '3.1.0', 'phase': 'R02.3',
                        'status': 'candidate'}

    def data(self, **changes):
        return json.dumps(self.version | changes).encode()

    def test_legacy_fields_and_distinct_versions(self):
        value = m.build_info(self.data(), b'VERSION="3.0.0"\n', 'a'*40)
        self.assertEqual(value, {'schema': m.BUILD_SCHEMA, 'candidate': 'V3.1.0',
            'version': '3.0.0', 'engine_version': '3.0.0',
            'release_version': '3.1.0', 'phase': 'R02.3', 'status': 'candidate',
            'commit': 'a'*40, 'contains_local_data': False})

    def test_invalid_metadata(self):
        for changes in ({'schema': 'unknown'}, {'status': 'released'},
                        {'release_version': '3.01.0'}, {'release_version': '2.9.0'},
                        {'phase': 'D08.3'}, {'private': 'fixture'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.read_version(self.data(**changes))

    def test_mismatch_and_invalid_commit_refused(self):
        for source, sha in ((b'VERSION="3.0.1"', 'a'*40),
                            (b'VERSION="3.0.0"', 'main'),
                            (b'VERSION="3.0.0"\nVERSION="3.0.0"', 'a'*40),
                            (b'VERSION=3', 'a'*40)):
            with self.subTest(source=source, sha=sha), self.assertRaises(ValueError):
                m.build_info(self.data(), source, sha)

    def test_actual_source_matches_declaration_without_import(self):
        root = Path(__file__).resolve().parent
        info = m.build_info((root/'release_version.json').read_bytes(),
                            (root/'serveur.py').read_bytes(), 'a'*40)
        self.assertEqual(info['version'], info['engine_version'])


if __name__ == '__main__':
    unittest.main()
