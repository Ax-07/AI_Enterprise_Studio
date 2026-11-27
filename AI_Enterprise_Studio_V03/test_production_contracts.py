"""Transverse production contracts on real SQLite, offline execution only."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import autopilot
import draft_recovery as recovery
import improvement as imp
import laboratory as lab
import moteur as m
import portfolio
import serveur as s
import verification as verifier
from infrastructure import providers


class ProductionFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        self.network=self.stack.enter_context(patch.object(s,'request',side_effect=AssertionError('unexpected provider')))
        self.stack.enter_context(patch.object(providers.urllib.request,'urlopen',side_effect=AssertionError('unexpected network')))
        s.init()
        self.cfg={**s.config(),'key':'fixture-key','brave':'fixture-brave','budget':2000000,
                  'mission_budget':750000,'call_limit':40,'turn_limit':10,'html_sandbox_enabled':False}

    def mission(self,title,ref=None):
        with s.db() as c:
            return m.create(s,c,title,'cloud',ref)

    def act(self,mid,agent,action,target='',text='',detail=''):
        with s.db() as c:
            tid=m.add_task(c,mid,agent,'Fixture')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
        return m.execute(s,t,dict(action=action,target=target,text=text,detail=detail),self.cfg,'cloud')

    def finish(self,mid):
        with s.db() as c:
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))

    def row(self,aid):
        with s.db() as c:
            return dict(imp.row(c,aid))

    def test_versioned_production_exact_audit_and_regression(self):
        mid=self.mission('Production')
        first=self.act(mid,'NEXUS','write_file','kit.csv','a,b\n1,2')
        second=self.act(mid,'NEXUS','write_file','kit.csv','a,b\n1,3')
        self.assertEqual((first['version'],second['version']),(1,2))
        self.finish(mid)
        audit=self.mission('Audit',second['fichier'])
        spec=json.dumps({'checks':[{'op':'sum','column':'b','expected':'3'}]})
        proof=self.act(audit,'SENTINEL','test_file','ref:'+str(second['fichier']),spec)
        self.assertEqual(proof['status'],'passed')
        self.finish(audit)
        with s.db() as c:
            base=imp.row(c,second['fichier'])
            frozen=imp.plan(c,base,'generic')
            self.assertEqual(frozen['replays'],[{'proof':proof['verification_id'],'spec':spec}])
            self.assertEqual(portfolio.evidence(c,base)[0]['status'],'passed')
            self.assertEqual(imp.row(c,first['fichier'])['content'],'a,b\n1,2')
            state,result=imp.verify_pair(base,{'name':'kit.csv','content':'a,b\n1,2'},frozen,'generic',self.cfg,None)
            self.assertEqual(state,'rejected')
            self.assertEqual(result['replays'][0]['result']['status'],'failed')
            self.assertEqual(s.used(c),0)
        self.network.assert_not_called()

    def test_static_success_is_not_functional_evidence_and_hash_is_exact(self):
        mid=self.mission('Production')
        result=self.act(mid,'NEXUS','write_file','kit.json','{"value":1}')
        aid=result['fichier']
        self.assertTrue(result['controle']['valide'])
        self.finish(mid)
        audit=self.mission('Audit',aid)
        spec=json.dumps({'checks':[{'op':'equals','path':['value'],'expected':1}]})
        with s.db() as c:
            self.assertEqual(portfolio.evidence(c,imp.row(c,aid)),[])
            with self.assertRaisesRegex(ValueError,'Aucune preuve'):
                imp.plan(c,imp.row(c,aid),'generic')
        self.act(audit,'SENTINEL','test_file','ref:'+str(aid),spec)
        self.finish(audit)
        with s.db() as c:
            self.assertEqual(len(imp.plan(c,imp.row(c,aid),'generic')['replays']),1)
            c.execute("UPDATE artifacts SET content=content||' ' WHERE id=?",(aid,))
            self.assertEqual(portfolio.evidence(c,imp.row(c,aid)),[])
            with self.assertRaisesRegex(ValueError,'Aucune preuve'):
                imp.plan(c,imp.row(c,aid),'generic')

    def test_real_benchmark_score_frozen_comparison_and_exact_hash(self):
        mid=self.mission('Catalogue')
        aid=self.act(mid,'NEXUS','write_file','audit_catalogue.html','<p>fixture</p>')['fichier']
        self.finish(mid)
        with patch.object(verifier,'browser_results') as browser:
            unavailable=lab.run(s,aid,lab.PROFILE,300,42,self.cfg)
            self.assertEqual(unavailable['status'],'unavailable')
            browser.assert_not_called()
        fixtures=lab.catalogue(300,42)
        observed=[{'name':f['name'],'passed':True,'elapsed_ms':25,
                   'output':f['expected_error'] if 'expected_error' in f else '\n'.join(f['expected']+[f['total']])}
                  for f in fixtures]
        enabled={**self.cfg,'html_sandbox_enabled':True}
        with patch.object(verifier,'browser_results',return_value=observed) as browser:
            baseline=lab.run(s,aid,lab.PROFILE,300,42,enabled)
            self.assertEqual(baseline['status'],'passed')
            self.assertEqual(baseline['metrics']['recall'],1)
            with s.db() as c:
                base=imp.row(c,aid)
                self.assertEqual(lab.canonical(c,base)['id'],baseline['id'])
                frozen=imp.plan(c,base,'generic')
                self.assertEqual(frozen,{'replays':[],'lab':baseline['id'],'profile':'generic'})
                state,result=imp.verify_pair(base,{'name':base['name'],'content':'<p>candidate</p>'},frozen,'generic',enabled,baseline)
                self.assertEqual(state,'review')
                self.assertTrue(result['laboratory']['non_regression'])
                self.assertEqual(s.used(c),0)
            self.assertEqual(browser.call_count,2)
            for call in browser.call_args_list:
                self.assertTrue(all(set(case)=={'name','input'} for case in call.args[1]))
        self.network.assert_not_called()

    def test_recovery_uses_fresh_exact_audit_without_rewriting(self):
        mid=self.mission('Interrupted production')
        aid=self.act(mid,'NEXUS','write_file','draft.json','{"value":1}')['fichier']
        with s.db() as c:
            a=imp.row(c,aid);digest=recovery.sha(a)
            pid=c.execute("INSERT INTO projects(origin,title) VALUES('fixture','Fixture')").lastrowid
            portfolio.attach(c,mid,pid,'fixture')
            cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('fixture',100000,1,'{}',0,'bloqué')").lastrowid
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'create')",(cid,mid))
            c.execute("UPDATE missions SET state='bloquée',error='Enveloppe Autopilote insuffisante pour réserver cet appel.' WHERE id=?",(mid,))
            c.execute("INSERT INTO events(mission,agent,action,args,result,ok) VALUES(?,'NEXUS','write_file',?,?,1)",
                      (mid,json.dumps({'text_sha256':digest}),json.dumps({'fichier':aid})))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'fixture',500,300,'mesuré')",(mid,))
            self.assertEqual(recovery.candidates(c)[0]['artifact'],aid)
            audit_cid=recovery.start(c,{'confirm':True,'artifact':aid,'sha256':digest,'budget':'0.10'},self.cfg)
            self.assertEqual(recovery.choose(c,audit_cid),('functional',aid,None))
            audit=m.create(s,c,'Independent audit','cloud',aid)
            portfolio.attach(c,audit,pid,'fixture audit')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'functional',?)",(audit_cid,audit,aid))
        with self.assertRaises(ValueError):
            self.act(audit,'NEXUS','write_file','draft.json','{}')
        with self.assertRaises(ValueError):
            self.act(audit,'SENTINEL','test_file','draft.json','{}')
        spec=json.dumps({'checks':[{'op':'equals','path':['value'],'expected':1}]})
        self.assertEqual(self.act(audit,'SENTINEL','test_file','ref:'+str(aid),spec)['status'],'passed')
        with s.db() as c:
            self.assertEqual(recovery.verdict(c,recovery.record(c,audit_cid)),'active')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(audit,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(audit_cid,))
            self.assertEqual(recovery.verdict(c,recovery.record(c,audit_cid)),'adopted')
            self.assertEqual(portfolio.latest(c,pid)['id'],aid)
            self.assertEqual(recovery.candidates(c),[])
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0],'bloquée')
            self.assertEqual(c.execute('SELECT state FROM campaigns WHERE id=?',(cid,)).fetchone()[0],'bloqué')
            self.assertEqual(recovery.sha(imp.row(c,aid)),digest)
            self.assertEqual(s.used(c),300)
        self.network.assert_not_called()


if __name__=='__main__':
    unittest.main()
