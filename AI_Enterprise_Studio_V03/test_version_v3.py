import json
import unittest
from pathlib import Path
import serveur as s
class VersionV3Tests(unittest.TestCase):
    def test_public_identity(self):
        self.assertEqual(s.VERSION,'3.0.0')
        root=Path(s.__file__).parent
        self.assertIn('V3.0.0',(root/'index.html').read_text(encoding='utf8'))
        self.assertIn('V3.0.0',(root/'interface/live.html').read_text(encoding='utf8'))
        self.assertEqual(json.loads((root/'interface/manifest.json').read_text(encoding='utf8'))['live']['application_version'],s.VERSION)
