import json,unittest,hashlib
from unittest.mock import patch
import serveur as s,autopilot as a,moteur as m,portfolio as p,planner as pl,periodic as pe,budgeting as b,draft_recovery as dr
import test_planner

class BudgetDraftTests(unittest.TestCase):
    setUp=test_planner.PlannerTests.setUp
    historical=test_planner.PlannerTests.historical
    assess=test_planner.PlannerTests.assess
    act=test_planner.PlannerTests.act
    reply=test_planner.PlannerTests.reply
    def fixture(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        with s.db() as c:
            cid=a.start(c,{'confirm':True,'goal':'Produire un brouillon','budget':'0.12','max_missions':1,'permissions':{'research':False,'production':True,'tests':True,'market':False},'project':new,'search_cap':0},self.cfg)
            mid=m.create(s,c,'Création exacte','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'create')",(cid,mid));p.attach(c,mid,new,'test')
            tid=m.add_task(c,mid,'NEXUS','Production')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
        action=self.act('write_file','draft.csv','a,b\n1,2','Brouillon synthétique')
        result=m.execute(s,t,action,self.cfg,'cloud')
        with s.db() as c:
            m.log(c,t,'write_file',m.action_args(action),result,True)
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent,stage) VALUES(?,'test',70000,47404,'mesuré','NEXUS',?)",(mid,tid))
            c.execute("UPDATE tasks SET turns=1 WHERE id=?",(tid,))
        return cid,mid,tid,new,result['fichier'],opp
    def block(self,cid,mid):
        with s.db() as c:
            error='Enveloppe Autopilote insuffisante pour réserver cet appel.'
            c.execute("UPDATE missions SET state='bloquée',error=? WHERE id=?",(error,mid))
            c.execute("UPDATE campaigns SET state='bloqué',reason=? WHERE id=?",(error,cid))
    def authorize(self,aid,**kw):
        with s.db() as c:
            sha=dr.sha(c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone())
            return dr.start(c,{'confirm':True,'artifact':aid,'sha256':sha,'budget':'0.25',**kw},self.cfg)
    def test_actual_outgoing_budget_fit_and_refusal(self):
        cid,mid,tid,project,aid,opp=self.fixture()
        cfg={**self.cfg,'mission_budget':750000}
        sent=[]
        def fake(url,headers,body=None):
            sent.append(body)
            return self.reply(self.act('finish',text='Brouillon enregistré'))
        prompt='x'*20000
        with patch.object(s,'request',side_effect=fake):
            s.call_model(mid,'NEXUS',prompt,cfg,8192,tid,schema=m.SCHEMA,rules=m.RULES,validator=m.validate_action)
        self.assertEqual(len(sent),1)
        self.assertEqual(sent[0]['max_output_tokens'],2048)
        with s.db() as c:
            x=b.history(c,mid)[0];self.assertEqual(x['decision'],'adapted')
            pi,po=s.PRICES[cfg['models']['NEXUS']]
            self.assertEqual(x['chosen_reserve'],b.estimate(sent[0],pi,po,2048))
            self.assertLessEqual(x['chosen_reserve'],x['available'])
            self.assertEqual(c.execute('SELECT limit_out FROM ledger ORDER BY id DESC LIMIT 1').fetchone()[0],2048)
        with patch.object(s,'request',side_effect=AssertionError('No network')) as req:
            with self.assertRaisesRegex(RuntimeError,'réservation minimale'):
                s.call_model(mid,'NEXUS','x'*100000,cfg,8192,tid,schema=m.SCHEMA,rules=m.RULES,validator=m.validate_action)
            req.assert_not_called()
        with s.db() as c:
            x=b.history(c,mid)[0];self.assertEqual(x['decision'],'refused');self.assertIsNone(x['chosen_tokens'])
            self.assertGreater(x['minimum_reserve'],x['available'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()[0],2)
    def test_fit_reduces_output_to_real_remaining_and_preserves_reservations(self):
        cid,mid,tid,project,aid,opp=self.fixture()
        with s.db() as c:
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',50000,'à rapprocher')",(mid,))
        seen=[]
        def fake(url,headers,body=None):
            seen.append(body);return self.reply(self.act('finish',text='Rapport'))
        with patch.object(s,'request',side_effect=fake) as req:
            with self.assertRaises(RuntimeError):
                s.call_model(mid,'NEXUS','x'*30000,self.cfg,8192,tid,schema=m.SCHEMA,rules=m.RULES,validator=m.validate_action)
            req.assert_not_called()
        with s.db() as c:
            self.assertEqual(a.costs(c,cid),97404)
            self.assertEqual(b.history(c,mid)[0]['available'],22596)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM ledger WHERE mission=? AND state='à rapprocher'",(mid,)).fetchone()[0],1)
    def test_recovery_real_engine_preserves_original_and_adopts_exact_proof(self):
        cid,mid,tid,project,aid,opp=self.fixture();self.block(cid,mid)
        with s.db() as c:
            self.assertIsNone(p.latest(c,project))
            self.assertEqual([x['artifact'] for x in dr.candidates(c)],[aid])
            orig=dict(a._campaign(c,cid));oldcost=a.costs(c,cid)
        with self.assertRaises(ValueError):self.authorize(aid,sha256='invalid')
        new=self.authorize(aid)
        actions=[self.act('delegate','SENTINEL','Tester exact','Assertions indépendantes'),
            self.act('read_file','ref:'+str(aid)),
            self.act('test_file','ref:'+str(aid),json.dumps({'checks':[{'op':'row_count','expected':1}]})),
            self.act('finish',text='Un contrôle synthétique réussi, autres cas non testés'),
            self.act('finish',text='Audit borné, pas de demande validée')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            self.assertNotIn('write_file',body['text']['format']['schema']['properties']['action']['enum'])
            return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req:
            a.worker(s,new)
        self.assertEqual(actions,[])
        self.assertEqual(req.call_count,5)
        with s.db() as c:
            self.assertEqual(dict(a._campaign(c,cid)),orig)
            self.assertEqual(a.costs(c,cid),oldcost)
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0],'bloquée')
            self.assertEqual(dr.history(c)[0]['verdict'],'adopted')
            self.assertEqual(p.latest(c,project)['id'],aid)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM artifacts WHERE mission=?',(mid,)).fetchone()[0],1)
            self.assertEqual(a.searches(c,new),0)
            audit=s.campaign_audit(c,self.cfg,new)
            self.assertEqual(audit['draft_recovery'][0]['artifact'],aid)
            self.assertTrue(audit['missions'][0]['budget_decisions'])
            self.assertEqual(dr.candidates(c),[])
        with self.assertRaises(ValueError):self.authorize(aid)
    def test_bad_proof_or_changed_content_not_adopted(self):
        cid,mid,tid,project,aid,opp=self.fixture();self.block(cid,mid)
        new=self.authorize(aid)
        actions=[self.act('delegate','SENTINEL','Tester','Assertions'),
            self.act('test_file','ref:'+str(aid),json.dumps({'checks':[{'op':'row_count','expected':9}]})),
            self.act('finish',text='Échec observé'),self.act('finish',text='Pas de validation')]
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=lambda *a,**kw:self.reply(actions.pop(0))):
            a.worker(s,new)
        self.assertEqual(actions,[])
        with s.db() as c:
            self.assertEqual(dr.history(c)[0]['verdict'],'failed')
            self.assertIsNone(p.latest(c,project))
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
            self.assertEqual(dr.history(c)[0]['verdict'],'modified')
            self.assertIsNone(p.latest(c,project))
    def test_eligibility_no_uncertain_effect_and_exact_memory(self):
        cid,mid,tid,project,aid,opp=self.fixture();self.block(cid,mid)
        with s.db() as c:
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',1000,'à rapprocher')",(mid,))
            self.assertEqual(dr.candidates(c),[])
        with s.db() as c:
            c.execute("UPDATE missions SET state='en cours' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='actif' WHERE id=?",(cid,))
        result=m.execute(s,t,self.act('memory','opportunity:'+str(opp)),self.cfg,'cloud')
        self.assertEqual([x['id'] for x in result['résultats']],[opp])
        self.assertIn('300 fiches',result['résultats'][0]['next_test'])
    def test_budget_fit_binary_search_actual_cap(self):
        cid,mid,tid,project,aid,opp=self.fixture()
        with s.db() as c:
            body={'model':'test','input':'x'*20000,'max_output_tokens':8192}
            cfg={**self.cfg,'budget':s.used(c)+28000}
            cap,reserve,error=b.fit(c,mid,tid,'NEXUS',body,1,5,cfg,s.used(c),a.link(c,mid))
            self.assertIsNone(error)
            self.assertGreaterEqual(cap,1024)
            self.assertLess(cap,2048)
            self.assertLessEqual(reserve,28000)
            self.assertGreater(b.estimate(body,1,5,cap+1),28000)
