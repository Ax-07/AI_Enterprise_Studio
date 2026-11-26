import json,unittest
from unittest.mock import patch
import serveur as s,autopilot as a,planner as pl,portfolio as p,intelligence as intel,moteur as m
from test_autopilot import AutopilotTests
from test_portfolio import PortfolioTests
from test_commercial import PLAN,ECO

class PlannerTests(unittest.TestCase):
    setUp=AutopilotTests.setUp
    act=AutopilotTests.act
    reply=AutopilotTests.reply
    historical=PortfolioTests.historical

    def authorize(self,**kw):
        with s.db() as c:
            return pl.start(c,{'confirm':True,'budget':'0.50','per_campaign':'0.25','max_campaigns':2,'search_cap':0,'explore':False,**kw},self.cfg)

    def assess(self,opp,units):
        with s.db() as c:
            mid=c.execute('SELECT mission FROM opportunities WHERE id=?',(opp,)).fetchone()[0]
            d={'price_cents':2500,'variable_cost_cents':1000,'fixed_month_cents':12000,'monthly_units':units,'automation_pct':80,'risk':4,'source_runs':[],'rationale':'Hypothèses non vérifiées, coûts et prix à confirmer.'}
            intel.assess(c,mid,'MIDAS',str(opp),json.dumps(d))

    def test_preview_exact_product_and_deficit_no_spend(self):
        *_,fixed,opp,old,new=self.historical()
        self.assess(opp,5)
        with s.db() as c:
            before=c.total_changes
            preview=pl.candidates(c)
            self.assertEqual(c.total_changes,before)
            self.assertEqual([(x['project'],x['artifact'],x['kind']) for x in preview['ready']],[(old,fixed,'commercial')])
            self.assertIn('non viable',next(x['reason'] for x in preview['held'] if x['project']==new))
            self.assertEqual(s.used(c),10000)
        self.assess(opp,10)
        with s.db() as c:
            self.assertEqual([(x['project'],x['kind']) for x in pl.candidates(c)['ready']],[(old,'commercial'),(new,'create')])

    def test_real_engine_serial_pipeline_and_history_export(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        pid=self.authorize()
        actions=[self.act('delegate','ORION','Étudier','Sans réseau'),self.act('finish',text='Sources insuffisantes'),
            self.act('delegate','HERMES','Préparer','Offre interne'),self.act('commercial_offer',text=json.dumps(PLAN)),
            self.act('finish',text='Protocole futur'),self.act('delegate','MIDAS','Évaluer','Hypothèses'),
            self.act('commercial_economics','1',json.dumps(ECO)),self.act('finish',text='Évaluation'),
            self.act('delegate','SENTINEL','Auditer','Limites'),self.act('commercial_review','1',json.dumps({'verdict':'study_further','gaps':'Preuves documentaires manquantes.'})),
            self.act('finish',text='Revue interne'),self.act('finish',text='Pas de lancement'),
            self.act('delegate','NEXUS','Prototype','Livrable interne'),self.act('write_file','prototype.csv','a,b\n1,2','Données synthétiques'),
            self.act('finish',text='Prototype interne'),self.act('finish',text='Aucune demande validée')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req,patch.object(m,'fetch_page',side_effect=AssertionError('No network')):
            pl.worker(s,pid)
        self.assertEqual(actions,[])
        self.assertEqual(req.call_count,16)
        with s.db() as c:
            status=pl.status(c)['plan']
            self.assertEqual(status['state'],'completed',status)
            self.assertEqual([(q['project'],q['kind']) for q in status['queue']],[(old,'commercial'),(new,'create')])
            self.assertEqual(status['searches'],0)
            self.assertGreater(status['spent'],0)
            self.assertLessEqual(status['spent'],500000)
            self.assertEqual(status['spent'],sum(a.costs(c,q['campaign']) for q in status['queue']))
            audit=s.plan_audit(c,self.cfg,pid)
            self.assertEqual(len(audit['campaigns']),2)
            offer=audit['campaigns'][0]['commercial'][0]['offer']
            self.assertFalse(offer['external_authorized']);self.assertEqual(offer['sales'],0)
            self.assertEqual(offer['economics']['adverse_parameters']['variable_cost_cents'],5400)
            self.assertEqual(offer['economics']['adverse_parameters']['monthly_units'],5)
            self.assertNotIn(old,[x['project'] for x in pl.candidates(c)['ready']])
            self.assertEqual(len(p.status(c)['projects']),2)
            self.assertEqual(audit['campaigns'][1]['missions'][0]['mission']['kind'],'create')

    def test_budget_stop_resume_and_restart(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        pid=self.authorize(budget='0.20',per_campaign='0.15')
        with s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            self.assertEqual(a._campaign(c,cid)['budget'],150000)
            with self.assertRaises(ValueError):pl.guard_manual(c)
            mid=m.create(s,c,'Offre','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,fixed))
            p.attach(c,mid,old,'test')
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',140000,140000,'mesuré')",(mid,))
            pl.stop(c,pid)
            self.assertEqual(pl.get(c,pid)['state'],'paused')
            self.assertEqual(a._campaign(c,cid)['state'],'arrêté')
            self.assertEqual(pl.totals(c,pid),(140000,0))
            pl.resume(c,pid,self.cfg)
            self.assertEqual(pl.next_campaign(c,pid,self.cfg),cid)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM enterprise_plan_queue WHERE plan=?',(pid,)).fetchone()[0],1)
            self.assertEqual(pl.totals(c,pid),(140000,0))
        # Actual server init: pauses both active plan and active campaign, no thread.
        with patch.object(s,'request',side_effect=AssertionError('No provider')) as net:s.init();net.assert_not_called()
        with s.db() as c:
            self.assertEqual(pl.get(c,pid)['state'],'paused')
            self.assertEqual(a._campaign(c,cid)['state'],'interrompu')
            pl.resume(c,pid,self.cfg)
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
            second=pl.next_campaign(c,pid,self.cfg)
            self.assertNotEqual(second,cid)
            self.assertEqual(a._campaign(c,second)['budget'],60000)
            self.assertEqual(pl.totals(c,pid),(140000,0))

    def test_blocked_campaign_stops_and_limits(self):
        *_,old,new=self.historical()
        for kw in ({'confirm':False},{'budget':'9.00'},{'per_campaign':'0.80'},{'max_campaigns':6},{'search_cap':11},{'explore':True}):
            with self.assertRaises(ValueError):self.authorize(**kw)
        pid=self.authorize()
        with s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            c.execute("UPDATE campaigns SET state='bloqué',reason='Incident test' WHERE id=?",(cid,))
            self.assertIsNone(pl.next_campaign(c,pid,self.cfg))
            self.assertEqual(pl.get(c,pid)['state'],'blocked')
            self.assertEqual(len(pl.queue(c,pid)),1)

    def test_no_repeat_no_candidate_and_exploration_cooldown(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,5)
        pid=self.authorize(search_cap=3,explore=True)
        with s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            self.assertEqual(pl.queue(c,pid)[0]['kind'],'commercial')
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
            second=pl.next_campaign(c,pid,self.cfg)
            self.assertEqual(pl.queue(c,pid)[1]['kind'],'opportunity')
            self.assertEqual(a._campaign(c,second)['search_cap'],3)
            mid=m.create(s,c,'Exploration','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(second,mid))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(second,))
            self.assertIsNone(pl.next_campaign(c,pid,self.cfg))
        pid2=self.authorize(search_cap=3,explore=True)
        with s.db() as c:
            self.assertIsNone(pl.next_campaign(c,pid2,self.cfg))
            self.assertEqual(pl.get(c,pid2)['state'],'completed')
            self.assertEqual(pl.queue(c,pid2),[])
