import json
import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch
import serveur as s
import prepare_update as u

class PrepareUpdateTests(unittest.TestCase):
    def test_side_by_side(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'old';source.mkdir();(source/'donnees').mkdir()
            (source/'serveur.py').write_text('# fixture',encoding='utf8')
            cfg=source/'config.json';cfg.write_text('{"openai_budget_usd":4,"openai_api_key":"private-fixture"}')
            db=source/'donnees'/u.DB_NAME
            with patch.object(s,'DB',db):
                s.init()
                with s.db() as c:
                    mid=c.execute("INSERT INTO missions(title,mode,state,engine) VALUES('fixture','cloud','en cours','dynamic')").lastrowid
                    c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',3000,1000,'mesuré')",(mid,))
                    c.execute("INSERT INTO reports(mission,step,agent,report) VALUES(?,0,'ATLAS','private-report')",(mid,))
            before=db.read_bytes()
            target=root/'candidate'
            with patch.object(u,'assert_offline'):
                with self.assertRaises(ValueError):u.prepare(source,target)
                report=u.prepare(source,target,confirmed=True)
                self.assertEqual(report['protected_tables']['ledger'],1)
                self.assertFalse(report['started'])
                self.assertNotIn('private',json.dumps(report))
                self.assertEqual(before,db.read_bytes())
                self.assertEqual(cfg.read_bytes(),(target/'config.json').read_bytes())
                with u.readonly(target/'donnees'/u.DB_NAME) as c:
                    self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'interrompue')
                    self.assertEqual(c.execute('SELECT SUM(actual) FROM ledger').fetchone()[0],1000)
                self.assertEqual(u.fingerprint(target.with_name('candidate-sauvegarde')/'donnees'/u.DB_NAME),u.fingerprint(db))
                with self.assertRaises(ValueError):u.prepare(source,target,confirmed=True)
