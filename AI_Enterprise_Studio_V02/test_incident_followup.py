import json,unittest,urllib.error
from unittest.mock import patch
import serveur as s,moteur as m,autopilot as a,planner as pl,portfolio as p,commercial as co,incidents
from test_planner import PlannerTests
from test_commercial import PLAN,ECO

class IncidentFollowupTests(unittest.TestCase):
    setUp=PlannerTests.setUp
    act=PlannerTests.act
    reply=PlannerTests.reply
    historical=PlannerTests.historical
    authorize=PlannerTests.authorize
    assess=PlannerTests.assess

    def seed_offer(self):
        *_,fixed,opp,old,new=self.historical();self.assess(opp,5)
        with s.db() as c:
            cid=a.start(c,{'confirm':True,'goal':'Offre initiale','budget':'0.25','max_missions':1,'permissions':{'research':True,'production':False,'tests':True,'market':True},'search_cap':0,'project':old,'commercial':True},self.cfg)
            mid=m.create(s,c,'Offre initiale','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,fixed))
            p.attach(c,mid,old,'test')
            oid=co.execute(c,{'mission':mid,'agent':'HERMES'},'commercial_offer','',json.dumps(PLAN),'')['offer']
            co.execute(c,{'mission':mid,'agent':'MIDAS'},'commercial_economics',str(oid),json.dumps(ECO),'')
            co.execute(c,{'mission':mid,'agent':'SENTINEL'},'commercial_review',str(oid),json.dumps({'verdict':'study_further','gaps':'Sources insuffisantes, aucune demande établie.'}),'')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
        return cid,mid,oid,old,new,fixed

    def test_documentary_complement_real_engine_mock_sources(self):
        cid,mid,oid,old,new,fixed=self.seed_offer()
        with s.db() as c:
            original=co.project_status(c,old)['offer']
            self.assertEqual(pl.candidates(c)['ready'],[])
            self.assertEqual(pl.candidates(c,3)['ready'][0]['base_offer'],oid)
        pid=self.authorize(search_cap=3)
        urls=['https://buyer.example/need','https://vendor.example/offer']
        quotes=['Les erreurs répétées coûtent du temps.','Forfait annoncé de cent euros.']
        actions=[self.act('delegate','ORION','Recherche documentaire','Sources exactes'),
            self.act('search',text='besoin et prix audit catalogue'),
            self.act('read',urls[0]),self.act('commercial_signal','1',json.dumps({'kind':'buyer_problem','quote':quotes[0],'interpretation':'Indice de besoin à vérifier.'})),
            self.act('read',urls[1]),self.act('commercial_signal','2',json.dumps({'kind':'competitor_price','quote':quotes[1],'interpretation':'Prix annoncé, pas volonté de payer.'})),
            self.act('finish',text='Deux indices documentaires synthétiques de test.'),
            self.act('delegate','SENTINEL','Revue','Compléter seulement les preuves'),
            self.act('commercial_extend',str(oid),json.dumps({'signal_ids':[1,2],'verdict':'propose_future_test','gaps':'Indices documentaires seulement, test futur à autoriser.','risks':'Risques de marché et conformité encore à vérifier.'})),
            self.act('finish',text='Revue limitée'),self.act('finish',text='Aucun lancement')]
        def fake(url,headers,body=None):
            if 'api.search.brave.com' in url:return {'web':{'results':[{'title':'Source test','url':v,'description':'Extrait'} for v in urls]}}
            self.assertIn('api.openai.com',url)
            return self.reply(actions.pop(0))
        def fetch(url):return {'url':url,'date':'2026-11-25','texte':quotes[urls.index(url)]+' '+('Document synthétique de test seulement. '*6),'partiel':False}
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake),patch.object(m,'fetch_page',side_effect=fetch):
            pl.worker(s,pid)
        self.assertEqual(actions,[])
        with s.db() as c:
            d=pl.status(c)['plan'];self.assertEqual(d['state'],'completed',d)
            self.assertEqual(len(d['queue']),1);self.assertEqual(d['searches'],1)
            follow=co.project_status(c,old)['offer']
            self.assertEqual(follow['base_offer'],oid)
            self.assertEqual(follow['state'],'proposition_a_examiner')
            self.assertEqual(follow['economics']['assumptions'],original['economics']['assumptions'])
            self.assertEqual(follow['economics']['result'],original['economics']['result'])
            self.assertEqual(follow['plan']['price_cents'],original['plan']['price_cents'])
            self.assertFalse(follow['external_authorized'])
            self.assertEqual(co.project_status(c,old,mid)['offer'],original)
            self.assertEqual(pl.candidates(c,3)['ready'],[])
            audit=s.plan_audit(c,self.cfg,pid)
            mission=audit['campaigns'][0]['missions'][0]
            self.assertEqual({x['agent'] for x in mission['tasks']},{'ATLAS','ORION','SENTINEL'})
            self.assertEqual(len(mission['ledger']),len(mission['events']))
            self.assertEqual(audit['campaigns'][0]['commercial'][0]['followup']['base_offer'],oid)

    def test_followup_requires_new_signal_and_forbids_repricing(self):
        _,mid,oid,old,new,fixed=self.seed_offer()
        pid=self.authorize(search_cap=3)
        with s.db() as c:
            cid=pl.next_campaign(c,pid,self.cfg)
            child=m.create(s,c,'Complément','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,child,fixed))
            p.attach(c,child,old,'test')
            t={'mission':child,'agent':'SENTINEL'}
            self.assertNotIn('commercial_offer',a.permitted(c,child,'HERMES',m.PERMS['HERMES'])[0])
            self.assertNotIn('commercial_economics',a.permitted(c,child,'MIDAS',m.PERMS['MIDAS'])[0])
            with self.assertRaises(ValueError):a.guard(c,child,'ATLAS','delegate','MIDAS',m.PERMS['ATLAS'])
            with self.assertRaises(ValueError):co.execute(c,t,'commercial_extend',str(oid),json.dumps({'signal_ids':[],'verdict':'propose_future_test','gaps':'Sources insuffisantes.','risks':'Risque inconnu.'}),'')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM commercial_offers').fetchone()[0],1)

    def test_transient_recovery_same_campaign_no_duplicate_reservation(self):
        *_,old,new=self.historical();pid=self.authorize(max_campaigns=1)
        calls=[]
        def fake(url,headers,body=None):
            calls.append(url)
            if len(calls)==1:raise urllib.error.HTTPError(url,503,'Unavailable',{},None)
            return self.reply(self.act('finish',text='Rapport partiel, aucun lancement.'))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake):pl.worker(s,pid)
        self.assertEqual(len(calls),2)
        with s.db() as c:
            d=pl.status(c)['plan'];self.assertEqual(d['state'],'completed',d)
            self.assertEqual(len(d['queue']),1)
            self.assertEqual(sum(e['event']=='recovered' for e in d['events']),1)
            cid=d['queue'][0]['campaign'];history=incidents.history(c,cid);self.assertEqual(len(history),1)
            ledger=list(c.execute('SELECT * FROM ledger WHERE mission=? ORDER BY id',(history[0]['mission'],)))
            self.assertEqual(len(ledger),2);self.assertIsNone(ledger[0]['actual'])
            self.assertEqual(ledger[0]['state'],'à rapprocher')
            self.assertEqual(d['spent'],ledger[0]['reserved']+ledger[1]['actual'])

    def _failure(self,exc,wanted):
        self.historical();pid=self.authorize(max_campaigns=1)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=exc) as req:
            pl.worker(s,pid);self.assertEqual(req.call_count,wanted)
        with s.db() as c:
            d=pl.status(c)['plan'];self.assertEqual(d['state'],'blocked',d)
            self.assertEqual(len(d['queue']),1)
            self.assertEqual(len(incidents.history(c,d['queue'][0]['campaign'])),wanted-1)

    def test_second_503_stops(self):
        self._failure(urllib.error.HTTPError('https://api.openai.com/v1/responses',503,'error',{},None),2)

    def test_401_not_retried(self):
        self._failure(urllib.error.HTTPError('https://api.openai.com/v1/responses',401,'error',{},None),1)

    def test_429_not_retried(self):
        self._failure(urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'error',{},None),1)

    def test_timeout_not_retried(self):
        self._failure(TimeoutError('uncertain'),1)

    def test_lexical_similarity_is_advisory_only(self):
        self.historical()
        with s.db() as c:
            x=p._get(c,'test:catalogue','Contrôle qualité de catalogues produits pour vendeurs e-commerce multilingues')
            y=p._get(c,'test:fiches','Contrôle qualité automatisé de fiches produits multilingues pour e-commerçants')
            before=c.total_changes
            self.assertTrue(any(r['projects']==[x,y] for r in pl.related(c)))
            self.assertEqual(c.total_changes,before)
