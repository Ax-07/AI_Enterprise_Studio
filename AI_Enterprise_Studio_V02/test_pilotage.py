import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import moteur as m, serveur as s, pilotage as p, verification as v

class Pilotage(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        patcher=patch.object(s,'DB',Path(tmp.name)/'db');patcher.start();self.addCleanup(patcher.stop)
        s.init();self.cfg={**s.config(),'key':'test','budget':2000000,'mission_budget':750000,'call_limit':24,'turn_limit':10,'html_sandbox_enabled':True}
    def get(self,**cfg):
        with s.db() as c:return p.plan(c,{**self.cfg,**cfg})
    def seed(self,state='terminée',name='prototype_shopify_correction_v2_fr_en.html'):
        with s.db() as c:
            self.mid=m.create(s,c,'Correction','cloud')
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,?,1,'NEXUS','<p>test</p>','test')",(self.mid,name)).lastrowid
            c.execute('UPDATE missions SET state=? WHERE id=?',(state,self.mid))
    def proof(self,status):
        with s.db() as c:
            return c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'PROPRIETAIRE',?,?)",(self.aid,self.mid,json.dumps(v.shopify_spec(),ensure_ascii=False),json.dumps({'status':status}))).lastrowid
    def test_no_cloud_or_active(self):
        self.assertEqual(self.get()['action'],'opportunity')
        self.seed('en cours')
        self.assertEqual(self.get()['action'],'wait')
    def test_pending_precedes_proof(self):
        self.seed()
        with s.db() as c:c.execute("INSERT INTO requests(mission,body) VALUES(?,'{}')",(self.mid,))
        self.assertEqual(self.get()['action'],'decisions')
    def test_local_verification_before_budget(self):
        self.seed('bloquée')
        r=self.get(budget=0);self.assertEqual(r['action'],'verify');self.assertEqual(r['artifact'],self.aid)
        self.assertEqual(self.get(html_sandbox_enabled=False)['action'],'files')
    def test_resume_after_proof_with_limits(self):
        self.seed('bloquée')
        vid=self.proof('passed')
        self.assertEqual(self.get()['action'],'resume')
        self.assertEqual(self.get()['proof'],vid)
        self.assertEqual(self.get(budget=0)['action'],'diagnostic')
        with s.db() as c:c.execute('UPDATE tasks SET turns=10 WHERE mission=?',(self.mid,))
        self.assertEqual(self.get()['action'],'diagnostic')
    def test_completed_proof_and_failed(self):
        self.seed();self.proof('passed')
        self.assertEqual(self.get()['action'],'market')
        self.proof('failed')
        self.assertEqual(self.get()['action'],'improve')
        self.assertEqual(self.get(budget=0)['action'],'review')
    def test_other_file_and_latest_version(self):
        self.seed(name='kit.csv');self.proof('passed')
        with s.db() as c:c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',2,'NEXUS','a,b','new')",(self.mid,))
        self.assertEqual(self.get()['action'],'functional')
        self.assertIsNone(self.get()['proof'])
    def test_read_only_no_provider(self):
        self.seed('bloquée')
        with patch.object(s,'request',side_effect=AssertionError('network')) as net,patch.object(v,'run',side_effect=AssertionError('execution')) as verifier:
            before=self.get()
            self.assertEqual(before,self.get())
            net.assert_not_called();verifier.assert_not_called()
        with s.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM missions').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)
