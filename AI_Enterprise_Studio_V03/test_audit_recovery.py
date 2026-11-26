import json,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import moteur as m, serveur as s, pilotage as p, recovery as r, verification as v

class AuditRecovery(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        pp=patch.object(s,'DB',Path(tmp.name)/'db');pp.start();self.addCleanup(pp.stop)
        s.init();self.cfg={**s.config(),'key':'fake','turn_limit':10,'budget':2000000,'mission_budget':750000}
        with s.db() as c:
            self.mid=m.create(s,c,'Correction Shopify','cloud')
            self.root=c.execute('SELECT id FROM tasks WHERE mission=?',(self.mid,)).fetchone()[0]
            self.nexus=m.add_task(c,self.mid,'NEXUS','Créer','',self.root)
            self.tid=m.add_task(c,self.mid,'SENTINEL','Vérifier','',self.root)
            c.execute("UPDATE tasks SET state='terminée',result='Produit' WHERE id=?",(self.nexus,))
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'prototype_shopify_correction_v2_fr_en.html',1,'NEXUS','<p>corrected</p>','test')",(self.mid,)).lastrowid
            self.spec=v.shopify_spec()
            self.result={'kind':'html','sha256':hashlib.sha256(b'<p>corrected</p>').hexdigest(),'status':'passed','checks':[{'name':x['name'],'passed':True} for x in self.spec['cases']]}
            self.vid=c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(self.aid,self.mid,json.dumps(self.spec),json.dumps(self.result))).lastrowid
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(self.tid,)).fetchone())
            m.log(c,t,'test_file',{},dict(self.result,verification_id=self.vid,fichier=self.aid),True)
            c.execute('UPDATE tasks SET turns=10 WHERE id=?',(self.tid,))
            c.execute("UPDATE missions SET state='bloquée',error=? WHERE id=?",('Plafond de tours atteint pour la tâche #'+str(self.tid),self.mid))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?,'test',1000,500,'mesuré','SENTINEL')",(self.mid,))
    def test_recover_provenance_and_no_cost(self):
        with patch.object(s,'request',side_effect=AssertionError('provider')) as net:
            with s.db() as c:
                self.assertEqual(p.plan(c,self.cfg)['action'],'close_audit')
                z=r.close(c,self.mid,self.tid,self.vid,self.cfg)
                self.assertFalse(z['paid_call'])
                t=c.execute('SELECT * FROM tasks WHERE id=?',(self.tid,)).fetchone()
                self.assertEqual((t['state'],t['turns']),('terminée',10))
                report=c.execute('SELECT * FROM reports').fetchone()
                self.assertEqual(report['agent'],'SYSTEME')
                self.assertEqual(json.loads(report['report'])['provenance'],'systeme_cloture_partielle')
                self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(self.mid,)).fetchone()[0],'prête')
                self.assertEqual(p.plan(c,self.cfg)['action'],'resume')
                self.assertEqual(s.used(c),500)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM verification_results').fetchone()[0],1)
                with self.assertRaises(ValueError):r.close(c,self.mid,self.tid,self.vid,self.cfg)
            net.assert_not_called()
    def test_refuse_owner_proof_or_wrong_event(self):
        with s.db() as c:
            c.execute("UPDATE verification_results SET agent='PROPRIETAIRE'")
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
            c.execute("UPDATE verification_results SET agent='SENTINEL'")
            c.execute('UPDATE events SET task=?',(self.root,))
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
    def test_refuse_changed_file_or_newer_failure(self):
        with s.db() as c:
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(self.aid,))
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
            c.execute("UPDATE artifacts SET content='<p>corrected</p>' WHERE id=?",(self.aid,))
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(self.aid,self.mid,json.dumps(self.spec),json.dumps(dict(self.result,status='failed'))))
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
    def test_refuse_wrong_scenario_or_unfinished(self):
        with s.db() as c:
            c.execute("UPDATE verification_results SET spec='{}'")
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
            c.execute('UPDATE verification_results SET spec=?',(json.dumps(self.spec),))
            c.execute('UPDATE tasks SET turns=9 WHERE id=?',(self.tid,))
            self.assertIsNone(r.candidate(c,self.mid,self.cfg))
    def test_final_turn_reserved(self):
        with s.db() as c:
            c.execute("UPDATE missions SET state='en cours' WHERE id=?",(self.mid,))
            c.execute('UPDATE tasks SET turns=9 WHERE id=?',(self.tid,))
        actions=[dict(action='finish',target='',text='4 tests réussis; autres critères non testés.',detail=''),dict(action='finish',target='',text='Conclusion avec limites.',detail='')]
        def fake(*args,**kwargs):
            a=actions.pop(0)
            if args[1]=='SENTINEL':
                self.assertEqual(kwargs['schema']['properties']['action']['enum'],['finish'])
                self.assertIn('DERNIER TOUR',args[2])
                self.assertFalse(kwargs['validator'](dict(a,action='read_file')))
                self.assertTrue(kwargs['validator'](a))
            return a
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'call_model',side_effect=fake):
            s.run(self.mid)
        with s.db() as c:
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(self.mid,)).fetchone()[0],'terminée')
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(self.tid,)).fetchone()[0],10)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM reports WHERE agent='SENTINEL'").fetchone()[0],1)
