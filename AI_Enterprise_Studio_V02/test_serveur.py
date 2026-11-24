import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import serveur as s
class Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.p=patch.object(s,'DB',Path(self.t.name)/'test.db');self.p.start();s.init()
        self.cfg={'key':'fake','brave':'','budget':2000000,'limit':10,'models':s.DEFAULT}
    def tearDown(self): self.p.stop();self.t.cleanup()
    def mission(self,mode='demo'):
        with s.db() as c:return c.execute("INSERT INTO missions(title,mode,state) VALUES('test',?,'en cours')",(mode,)).lastrowid
    def test_demo(self):
        mid=self.mission()
        with patch.object(s,'request',side_effect=AssertionError('network')),patch.object(s,'config',return_value=self.cfg):s.run(mid)
        with s.db() as c:
            self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'terminée');self.assertEqual(c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],5);self.assertEqual(s.used(c),0);self.assertEqual(c.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)
    def test_budget_blocks(self):
        mid=self.mission('cloud');cfg={**self.cfg,'budget':1}
        with patch.object(s,'request') as r:
            with self.assertRaises(RuntimeError):s.call_model(mid,'ATLAS','test',cfg)
            r.assert_not_called()
    def test_usage(self):
        mid=self.mission('cloud');v=s.MOCK[0];response={'status':'completed','usage':{'input_tokens':1000,'output_tokens':500},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(v)}]}]}
        with patch.object(s,'request',return_value=response):self.assertEqual(s.call_model(mid,'ATLAS','test',self.cfg),v)
        with s.db() as c:self.assertEqual(s.used(c),7000)
    def test_failed_reservation(self):
        mid=self.mission('cloud')
        with patch.object(s,'request',side_effect=TimeoutError):
            with self.assertRaises(RuntimeError):s.call_model(mid,'ATLAS','test',self.cfg)
        with s.db() as c:self.assertGreater(s.used(c),0);self.assertEqual(c.execute('SELECT state FROM ledger').fetchone()[0],'à rapprocher')
    def test_restart(self):
        self.mission();s.init()
        with s.db() as c:self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'interrompue')
    def test_stopped(self):
        mid=self.mission('cloud')
        with s.db() as c:c.execute("UPDATE missions SET state='arrêtée'")
        with patch.object(s,'request') as r:
            with self.assertRaises(RuntimeError):s.call_model(mid,'ATLAS','test',self.cfg)
            r.assert_not_called()
    def test_search_quota(self):
        mid=self.mission('cloud');cfg={**self.cfg,'brave':'fake','limit':1}
        with patch.object(s,'request',return_value={'web':{'results':[{'title':'T','url':'https://example.com','description':'D'}]}}) as r:
            self.assertEqual(len(s.search(mid,['one','two'],cfg)),1);self.assertEqual(r.call_count,1)
    def test_incomplete(self):
        mid=self.mission('cloud')
        with patch.object(s,'request',return_value={'status':'incomplete','usage':{'input_tokens':100,'output_tokens':2400}}):
            with self.assertRaises(RuntimeError):s.call_model(mid,'ATLAS','test',self.cfg)
        with s.db() as c:self.assertGreater(s.used(c),0)
if __name__=='__main__':unittest.main()
