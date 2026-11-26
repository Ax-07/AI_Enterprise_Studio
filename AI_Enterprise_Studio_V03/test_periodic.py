import json,unittest,threading,urllib.request,urllib.error
from unittest.mock import patch
import serveur as s,periodic as pe,planner as pl,autopilot as a,moteur as m,portfolio as p,research
import test_planner
from test_commercial import PLAN,ECO

class PeriodicTests(unittest.TestCase):
    setUp=test_planner.PlannerTests.setUp
    historical=test_planner.PlannerTests.historical
    assess=test_planner.PlannerTests.assess
    act=test_planner.PlannerTests.act
    reply=test_planner.PlannerTests.reply
    T=1800000000
    def grant_body(self,**kw):
        return {'confirm':True,'cadence':'daily','periods':3,'total_budget':'0.50','period_budget':'0.25','per_campaign':'0.25','max_campaigns':1,'total_search':0,'period_search':0,'explore':False,**kw}
    def authorize(self,**kw):
        with s.db() as c:return pe.authorize(c,self.grant_body(**kw),self.cfg,self.T)
    def tick(self,t=None,locked=False):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            return pe.tick(c,self.cfg,self.T if t is None else t,locked)
    def test_real_engine_two_periods_no_duplicate_and_history(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        gid=self.authorize()
        self.assertIsNone(self.tick(locked=True))
        first=self.tick();self.assertIsNotNone(first)
        self.assertIsNone(self.tick())
        actions=[self.act('delegate','ORION','Étude','Sans réseau'),self.act('finish',text='Sources insuffisantes'),
            self.act('delegate','HERMES','Offre','Préparation interne'),self.act('commercial_offer',text=json.dumps(PLAN)),
            self.act('finish',text='Protocole futur'),self.act('delegate','MIDAS','Évaluer','Hypothèses'),
            self.act('commercial_economics','1',json.dumps(ECO)),self.act('finish',text='Évaluation'),
            self.act('delegate','SENTINEL','Auditer','Limites'),self.act('commercial_review','1',json.dumps({'verdict':'study_further','gaps':'Preuves documentaires manquantes.'})),
            self.act('finish',text='Revue interne'),self.act('finish',text='Pas de lancement'),
            self.act('delegate','NEXUS','Prototype','Livrable interne'),self.act('write_file','prototype.csv','a,b\n1,2','Données synthétiques'),
            self.act('finish',text='Prototype interne'),self.act('finish',text='Aucune demande validée')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req:
            with patch.object(pe,'now',return_value=self.T):pl.worker(s,first)
            self.assertEqual(req.call_count,12)
            self.assertIsNone(self.tick(self.T+10))
            # Missed second period: no catch-up, current third period only.
            second=self.tick(self.T+2*86400)
            self.assertIsNotNone(second)
            with patch.object(pe,'now',return_value=self.T+2*86400):pl.worker(s,second)
            self.assertEqual(req.call_count,16)
        self.assertEqual(actions,[])
        with s.db() as c:
            st=pe.status(c,self.cfg,gid)['grant']
            self.assertEqual([x['slot'] for x in st['slots']],[0,2])
            self.assertEqual([pl.get(c,x['plan'])['state'] for x in st['slots']],['completed','completed'])
            self.assertEqual([(pl.queue(c,x['plan'])[0]['project'],pl.queue(c,x['plan'])[0]['kind']) for x in st['slots']],[(old,'commercial'),(new,'create')])
            self.assertEqual(st['spent'],sum(pl.totals(c,x['plan'])[0] for x in st['slots']))
            self.assertEqual(st['searches'],0)
            self.assertLess(st['spent'],st['total_budget'])
            self.assertEqual(s.plan_audit(c,self.cfg,first)['planner']['plan']['id'],first)
            self.assertFalse(s.plan_audit(c,self.cfg,first)['campaigns'][0]['commercial'][0]['offer']['external_authorized'])
        self.assertIsNone(self.tick(self.T+3*86400))
        with s.db() as c:self.assertEqual(pe.latest(c)['state'],'expired')
    def setup_active(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        gid=self.authorize(total_search=2,period_search=1)
        pid=self.tick()
        with patch.object(pe,'now',return_value=self.T),s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            mid=m.create(s,c,'Étude','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,fixed))
            p.attach(c,mid,old,'test')
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',12000,'à rapprocher')",(mid,))
        return gid,pid,cid,mid
    def test_expiry_refuses_new_reservation_and_search_then_stops(self):
        gid,pid,cid,mid=self.setup_active()
        with patch.object(pe,'now',return_value=self.T+86400),s.db() as c:
            with self.assertRaisesRegex(ValueError,'hors période'):a.reserve(c,mid,100)
            with self.assertRaisesRegex(ValueError,'hors période'):a.search_allowed(c,mid)
            with self.assertRaisesRegex(ValueError,'hors période'):pl.next_campaign(c,pid,self.cfg)
        self.assertIsNone(self.tick(self.T+86400))
        with s.db() as c:
            self.assertEqual(pe.latest(c)['state'],'suspended')
            self.assertEqual(pl.get(c,pid)['state'],'abandoned')
            self.assertEqual(a._campaign(c,cid)['state'],'arrêté')
            self.assertEqual(pl.totals(c,pid),(12000,0))
            with self.assertRaises(ValueError):pe.deny_manual_campaign_resume(c,cid)
        self.assertIsNone(self.tick(self.T+2*86400))
    def test_revoke_preserves_reservations_and_disables_manual_bypass(self):
        gid,pid,cid,mid=self.setup_active()
        with s.db() as c:
            with self.assertRaises(ValueError):pe.guard_manual(c)
            pe.revoke(c,gid,self.T+1)
            self.assertEqual(pe.latest(c)['state'],'revoked')
            self.assertEqual(pl.get(c,pid)['state'],'abandoned')
            self.assertEqual(pl.totals(c,pid),(12000,0))
            with self.assertRaises(ValueError):pe.deny_manual_plan_resume(c,pid)
            with self.assertRaises(ValueError):pe.deny_manual_campaign_resume(c,cid)
            pe.guard_manual(c)
        self.assertIsNone(self.tick(self.T+86400))
    def test_restart_and_clock_rollback(self):
        gid,pid,cid,mid=self.setup_active()
        with patch.object(pe,'now',return_value=self.T+1),patch.object(s,'request',side_effect=AssertionError('No provider')) as req:s.init();req.assert_not_called()
        self.assertIsNone(self.tick(self.T+86400))
        with s.db() as c:
            self.assertEqual(pe.latest(c)['state'],'suspended')
            self.assertEqual(pl.get(c,pid)['state'],'paused')
            self.assertEqual(a._campaign(c,cid)['state'],'interrompu')
            self.assertEqual(pl.totals(c,pid),(12000,0))
            with self.assertRaises(ValueError):pe.deny_manual_plan_resume(c,pid)
            pe.revoke(c,gid,self.T+2)
            pl.abandon(c,pid)
        second=self.authorize()
        self.assertNotEqual(gid,second)
        self.assertIsNone(self.tick(self.T-1))
        with s.db() as c:self.assertEqual(pe.latest(c)['state'],'suspended')
    def test_budget_quota_and_no_candidate_no_calls(self):
        with patch.object(s,'request',side_effect=AssertionError('No provider')) as req:
            for kw in ({'confirm':False},{'total_budget':'3.00'},{'period_budget':'0.51'},{'per_campaign':'0.26'},{'total_budget':'0.80'},{'periods':13},{'period_search':1,'total_search':4},{'explore':True},{'cadence':'minute'}):
                with self.assertRaises(ValueError):self.authorize(**kw)
            gid=self.authorize()
            self.assertIsNone(self.tick())
            with s.db() as c:
                self.assertEqual(pe.latest(c)['state'],'exhausted')
                self.assertEqual(pe.slots(c,gid),[])
                self.assertEqual(s.used(c),0)
                self.assertIsNone(pl.latest(c))
            req.assert_not_called()
    def test_total_cap_and_no_repeat_across_periods(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,10)
        gid=self.authorize(total_budget='0.30',total_search=3,period_search=2)
        pid=self.tick()
        with patch.object(pe,'now',return_value=self.T),s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            mid=m.create(s,c,'Étude','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,fixed))
            p.attach(c,mid,old,'test')
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',240000,240000,'mesuré')",(mid,))
            for i in range(2):c.execute("INSERT INTO searches(mission,query,status) VALUES(?,?,'échec')",(mid,str(i)))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
            self.assertIsNone(pl.next_campaign(c,pid,self.cfg))
        second=self.tick(self.T+86400)
        with patch.object(pe,'now',return_value=self.T+86400),s.db() as c:
            row=pl.get(c,second)
            self.assertEqual(row['budget'],60000)
            self.assertEqual(row['per_campaign'],60000)
            self.assertEqual(row['search_cap'],1)
            cid2=pl.next_campaign(c,second,self.cfg)
            self.assertEqual(pl.queue(c,second)[0]['project'],new)
            self.assertEqual(a._campaign(c,cid2)['search_cap'],0)
            self.assertEqual(pe.status(c,self.cfg,gid)['grant']['remaining'],60000)
    def test_http_authorize_revoke_export_and_manual_guard(self):
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as req:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];url=f'http://127.0.0.1:{port}'
            def post(path,body,auth=True):
                h={'Content-Type':'application/json'}
                if auth:h['X-Session']=s.SESSION
                with urllib.request.urlopen(urllib.request.Request(url+'/api/'+path,data=json.dumps(body).encode(),headers=h)) as r:return json.load(r)
            try:
                with patch.object(s,'PORT',port):
                    with self.assertRaises(urllib.error.HTTPError) as err:post('periodic/authorize',self.grant_body(),False)
                    self.assertEqual(err.exception.code,403)
                    gid=post('periodic/authorize',self.grant_body())['grant']
                    with self.assertRaises(urllib.error.HTTPError) as err:post('start',{'mode':'demo','title':'Interdit pendant autorisation'})
                    self.assertEqual(err.exception.code,400)
                    with urllib.request.urlopen(urllib.request.Request(url+f'/api/periodic_audit?id={gid}',headers={'X-Session':s.SESSION})) as r:
                        d=json.load(r);self.assertEqual(d['periodic']['grant']['state'],'active');self.assertNotIn(s.SESSION,json.dumps(d))
                    post('periodic/revoke',{'confirm':True,'id':gid})
                    with s.db() as c:self.assertEqual(pe.latest(c)['state'],'revoked')
                    req.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()
    def test_exact_local_quote_fragments_are_not_signals(self):
        with s.db() as c:
            mid=m.create(s,c,'Étude','cloud')
            raw='Introduction '+('Texte de démonstration. '*6)+'\nPricing\n $ 64 / month\n Customers save hours on manual tasks. '+('Fin de page. '*8)
            c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,'https://example.com/','reçue',?)",(mid,json.dumps({'texte':raw})))
            other=m.create(s,c,'Autre','cloud')
            c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,'https://other.example/','reçue',?)",(other,json.dumps({'texte':'Autre texte '+raw})))
            result=research.exact_candidates(c,mid)
            self.assertEqual(len(result),1)
            self.assertTrue(result[0]['candidates'])
            for x in result[0]['candidates']:self.assertEqual(x['quote'],raw[x['offset']:x['offset']+len(x['quote'])])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM commercial_signals').fetchone()[0],0)
            self.assertEqual(s.used(c),0)
