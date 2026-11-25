import hashlib,json,unittest
from unittest.mock import patch
import test_autopilot
import serveur as s,moteur as m,autopilot as a,portfolio as p

class PortfolioTests(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    def historical(self):
        with s.db() as c:
            orig=m.create(s,c,'Prototype existant','cloud')
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'original.csv',1,'NEXUS','a,b\n1,2','test')",(orig,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(orig,))
            correction=m.create(s,c,'Correction','cloud',aid)
            fixed=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'corrige.csv',1,'NEXUS','a,b\n1,2','test')",(correction,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(correction,))
            audit=m.create(s,c,'Audit exact','cloud',fixed)
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(audit,))
            result={'kind':'csv','status':'passed','sha256':hashlib.sha256(b'a,b\n1,2').hexdigest(),'checks':[{'name':'Lignes','passed':True}]}
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(fixed,audit,'{"checks":[]}',json.dumps(result)))
            oppmid=m.create(s,c,'Diversification','cloud')
            opp=c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,'Audit de catalogues','Hypothèse, pas de demande prouvée','Tester 300 fiches synthétiques')",(oppmid,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(oppmid,))
            for mid,cost in [(orig,1000),(correction,2000),(audit,3000),(oppmid,4000)]:
                c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',?,?,'mesuré')",(mid,cost,cost))
            demo=m.create(s,c,'Simulation','demo')
            c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,'Fictive','Simulation','Aucun')",(demo,))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(demo,))
            p.sync(c)
            projects=p.status(c)['projects']
            return orig,correction,audit,oppmid,fixed,opp,projects[0]['id'],projects[1]['id']
    def test_migration_costs_lineage_and_no_duplicate(self):
        orig,correction,audit,oppmid,fixed,opp,old,new=self.historical()
        with s.db() as c:
            p.sync(c);p.sync(c)
            data=p.status(c)
            self.assertEqual(len(data['projects']),2)
            x,y=data['projects']
            self.assertEqual({r['id'] for r in x['missions']},{orig,correction,audit})
            self.assertEqual(x['latest_artifact'],fixed)
            self.assertEqual(x['spent'],6000);self.assertEqual(y['spent'],4000)
            self.assertEqual(y['opportunity'],opp)
            self.assertEqual(x['proofs'][0]['status'],'passed')
            self.assertEqual(data['unallocated'],0)
            self.assertEqual(sum(r['spent'] for r in data['projects']),s.used(c))
            self.assertEqual(y['next_kind'],'create')
    def test_ambiguous_discovery_cost_not_duplicated(self):
        with s.db() as c:
            mid=m.create(s,c,'Plusieurs idées','cloud')
            for title in ('A','B'):
                c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,'Hypothèse','Test')",(mid,title))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',5000,'à rapprocher')",(mid,))
            p.sync(c);data=p.status(c)
            self.assertEqual(len(data['projects']),2)
            self.assertEqual(data['unallocated'],5000)
            self.assertEqual(sum(x['spent'] for x in data['projects']),0)
    def test_selected_opportunity_ignores_other_product_and_runs_three_steps(self):
        orig,correction,audit,oppmid,fixed,opp,old,new=self.historical()
        cid=self.start(project=new)
        with s.db() as c:
            campaign=a._campaign(c,cid)
            self.assertIsNone(campaign['source'])
            self.assertEqual(p.scope(c,cid)['project'],new)
            choice,_=a.choose(c,campaign)
            self.assertEqual(choice[0],'create')
            self.assertEqual(choice[2]['id'],opp)
            self.assertIn('300 fiches synthétiques',a.title(campaign,*choice))
            with self.assertRaises(ValueError):p.set_state(c,new,'paused')
        spec=json.dumps({'checks':[{'op':'row_count','expected':1}]})
        actions=[self.act('delegate','NEXUS','Créer un prototype','Testable'),
          self.act('write_file','nouveau.csv','x,y\n1,2','Synthétique'),
          self.act('finish',text='Prototype interne'),self.act('finish',text='Production'),
          self.act('delegate','SENTINEL','Tester','Critère'),
          self.act('test_file','dynamic',spec),self.act('finish',text='Test limité'),self.act('finish',text='Audit'),
          self.act('delegate','HERMES','Étude','Sans réseau'),self.act('finish',text='Demande inconnue'),self.act('finish',text='Étude hypothétique')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            value=actions.pop(0)
            if value['target']=='dynamic':
                with s.db() as c:value['target']='ref:'+str(p.latest(c,new)['id'])
            return self.reply(value)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req:
            a.worker(s,cid)
        self.assertEqual(actions,[])
        self.assertEqual(req.call_count,11)
        with s.db() as c:
            state=a.status(c,self.cfg)
            self.assertEqual(state['state'],'terminé')
            self.assertEqual([x['kind'] for x in state['missions']],['create','functional','market'])
            self.assertTrue(all(x['state']=='terminée' for x in state['missions']))
            data=p.status(c);x,y=data['projects']
            self.assertEqual(x['spent'],6000)
            self.assertEqual(y['spent'],4000+state['spent'])
            self.assertNotEqual(y['latest_artifact'],fixed)
            self.assertEqual(y['market_studies'],1)
            self.assertIsNone(y['next_kind'])
            self.assertEqual(y['proofs'][0]['status'],'passed')
    def test_selection_pause_explore_and_historical_proof(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            p.set_state(c,old,'paused')
            self.assertEqual(p.recommend(c,dict.fromkeys(a.FLAGS,True))['id'],new)
            with self.assertRaises(ValueError):p.select(c,old,dict.fromkeys(a.FLAGS,True))
            p.set_state(c,old,'active')
            step,_=p.next_step(c,old,dict.fromkeys(a.FLAGS,True))
            self.assertEqual(step,('market',fixed,None))
        cid=self.start(project='explore')
        with s.db() as c:
            self.assertIsNone(a._campaign(c,cid)['source'])
            self.assertEqual(a.choose(c,a._campaign(c,cid))[0],('opportunity',None,None))
    def test_failed_proof_not_market_and_changed_hash_not_reused(self):
        *_,fixed,opp,old,new=self.historical()
        flags=dict.fromkeys(a.FLAGS,True)
        with s.db() as c:
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(fixed,))
            self.assertEqual(p.next_step(c,old,flags)[0][0],'functional')
            result={'status':'failed','sha256':hashlib.sha256(b'changed').hexdigest(),'checks':[{'name':'Échec','passed':False}]}
            mid=c.execute('SELECT mission FROM artifacts WHERE id=?',(fixed,)).fetchone()[0]
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL','{}',?)",(fixed,mid,json.dumps(result)))
            self.assertEqual(p.next_step(c,old,flags)[0][0],'improve')
