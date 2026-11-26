import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hashlib
import apply_design_patch as a

class DesignPatchTests(unittest.TestCase):
    def test_apply_restore_and_refuse(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'offline'):
            root=Path(tmp)/'app';package=Path(tmp)/'patch'
            (root/'interface').mkdir(parents=True);(root/'donnees').mkdir()
            (package/'payload'/'interface').mkdir(parents=True)
            private={'donnees/enterprise.sqlite3':b'fixture database untouched','config.json':b'fixture config untouched','PREPARATION.json':b'{}'}
            for n,v in private.items():(root/n).write_bytes(v)
            entries={}
            for n in a.FILES:
                old=None if 'original' in n or n.endswith('.bat') else ('old:'+n).encode()
                new=('new:'+n).encode()
                if old is not None:(root/n).write_bytes(old)
                (package/'payload'/n).write_bytes(new)
                entries[n]={'before':hashlib.sha256(old).hexdigest() if old is not None else None,'after':hashlib.sha256(new).hexdigest()}
            (package/'PATCH.json').write_text(json.dumps({'schema':a.SCHEMA,'base':a.BASE,'files':entries}))
            (root/'serveur.py').write_bytes(b'custom')
            with self.assertRaises(ValueError):a.apply(root,package,confirmed=True)
            self.assertFalse(root.with_name(root.name+'-sauvegarde-design-F06').exists())
            (root/'serveur.py').write_bytes(b'old:serveur.py')
            with self.assertRaises(ValueError):a.apply(root,package)
            original_put=a.put
            def interrupt(src,dst):
                if src.is_relative_to(package) and dst.name=='campus_preview.py':raise OSError('interruption fixture')
                original_put(src,dst)
            with patch.object(a,'put',side_effect=interrupt):
                with self.assertRaises(OSError):a.apply(root,package,confirmed=True)
            for n,e in entries.items():self.assertEqual(a.digest(root/n),e['before'])
            self.assertTrue(a.apply(root,package,confirmed=True,rollback=True)['restored'])
            import shutil
            shutil.rmtree(root.with_name(root.name+'-sauvegarde-design-F06')) # fixture only
            self.assertTrue(a.apply(root,package,confirmed=True)['installed'])
            for n,e in entries.items():self.assertEqual(a.digest(root/n),e['after'])
            with self.assertRaises(ValueError):a.apply(root,package,confirmed=True)
            self.assertTrue(a.apply(root,package,confirmed=True,rollback=True)['restored'])
            for n,e in entries.items():self.assertEqual(a.digest(root/n),e['before'])
            for n,v in private.items():self.assertEqual((root/n).read_bytes(),v)

    def test_rollback_partial(self):
        # The real archive apply/restore is additionally exercised in CI.
        self.assertNotIn('config.json',a.FILES)
        self.assertFalse(any(n.startswith('donnees/') for n in a.FILES))
