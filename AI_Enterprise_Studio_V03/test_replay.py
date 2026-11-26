import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import moteur as m, serveur as s, verification as v

class ReplayTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=patch.object(s,'DB',Path(tmp.name)/'db');p.start();self.addCleanup(p.stop)
        s.init();self.cfg=s.config()
        with s.db() as c:
            self.original=m.create(s,c,'Original','cloud')
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'prototype_rapprochement_shopify_fr_en.html',1,'NEXUS','<p>original</p>','test')",(self.original,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(self.original,))
            self.mid=m.create(s,c,'Correction','cloud',self.aid)
            self.fixed=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'prototype_shopify_correction_v2_fr_en.html',1,'NEXUS','<p>corrected</p>','test')",(self.mid,)).lastrowid
            self.tid=m.add_task(c,self.mid,'SENTINEL','Rejouer les tests')
            self.task=dict(c.execute('SELECT * FROM tasks WHERE id=?',(self.tid,)).fetchone())
        self.proof=m.quick_verify(s,self.aid,{**self.cfg,'html_sandbox_enabled':False})
    def test_replay_exact_spec(self):
        with patch.object(v,'run',return_value={'status':'passed','checks':[],'sha256':'fake'}) as run:
            a={'action':'test_file','target':'prototype_shopify_correction_v2_fr_en.html','text':'replay:'+str(self.proof['verification_id']),'detail':''}
            r=m.execute(s,self.task,a,self.cfg,'cloud')
            self.assertEqual(r['fichier'],self.fixed)
            self.assertEqual(json.loads(run.call_args.args[2]),v.shopify_spec())
        with s.db() as c:
            p=m.verification_context(c,self.mid)
            self.assertEqual({x['artifact'] for x in p},{self.aid,self.fixed})
            self.assertEqual(s.used(c),0)
    def test_replay_scope(self):
        with s.db() as c:
            other=m.create(s,c,'Sans référence','cloud')
            row=c.execute('SELECT * FROM artifacts WHERE id=?',(self.fixed,)).fetchone()
            with self.assertRaises(ValueError):m.verification_spec(c,other,row,'replay:'+str(self.proof['verification_id']))
    def test_corrected_filename(self):
        r=m.quick_verify(s,self.fixed,{**self.cfg,'html_sandbox_enabled':False},'shopify')
        self.assertEqual(r['status'],'unavailable')
        self.assertEqual(r['fichier'],self.fixed)
    def test_long_distinct_actions_and_legacy(self):
        a={'action':'test_file','target':'x.html','text':'a'*250+'1','detail':''}
        b={**a,'text':'a'*250+'2'}
        with s.db() as c:
            m.log(c,self.task,a['action'],{**a,'text':a['text'][:250]},{},True)
            self.assertEqual(m.repeat_count(c,self.tid,b),0)
            m.log(c,self.task,a['action'],m.action_args(a),{},True)
            self.assertEqual(m.repeat_count(c,self.tid,a),1)
            self.assertEqual(m.repeat_count(c,self.tid,b),0)
            short={**a,'text':'preset:shopify'}
            m.log(c,self.task,a['action'],short,{},True)
            self.assertEqual(m.repeat_count(c,self.tid,short),1)
