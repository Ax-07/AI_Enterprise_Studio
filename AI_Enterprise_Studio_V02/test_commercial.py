import json,unittest
from unittest.mock import patch
import serveur as s,moteur as m,autopilot as a,portfolio as p,commercial as co
from test_portfolio import PortfolioTests
from test_autopilot import AutopilotTests

PLAN={'audience':'Petits vendeurs','problem':'Erreurs de catalogue','offer':'Rapport de contrôle privé',
      'deliverables':'Rapport CSV','price_cents':10000,'channel':'Page future avec consentement',
      'metric':'qualified_interest','sample_size':20,'success_min':3,'duration_days':14,'signal_ids':[],
      'risks':'Arrêt si seuil non atteint; vérifier conformité et confidentialité.'}
ECO={'variable_cost_cents':4500,'fixed_month_cents':11000,'monthly_units':10,
     'rationale':'Hypothèses de cotisations, assistance, acquisition, retours et frais à vérifier.'}

class CommercialTests(unittest.TestCase):
    setUp=AutopilotTests.setUp
    start=AutopilotTests.start
    act=AutopilotTests.act
    reply=AutopilotTests.reply
    historical=PortfolioTests.historical

    def prepare(self,pid,**kwargs):
        return self.start(project=pid,commercial=True,max_missions=1,
            permissions={'research':True,'production':False,'tests':True,'market':True},**kwargs)

    def test_pipeline_and_export_no_external_calls(self):
        *_,old,new=self.historical()
        cid=self.prepare(old,search_cap=0)
        actions=[self.act('delegate','ORION','Étudier','Pas de réseau'),self.act('finish',text='Aucune preuve documentaire'),
          self.act('delegate','HERMES','Préparer','Offre interne'),self.act('commercial_offer',text=json.dumps(PLAN)),
          self.act('finish',text='Protocole futur'),self.act('delegate','MIDAS','Évaluer','Hypothèses'),
          self.act('commercial_economics','1',json.dumps(ECO)),self.act('finish',text='Scénarios'),
          self.act('delegate','SENTINEL','Auditer','Lacunes'),
          self.act('commercial_review','1',json.dumps({'verdict':'study_further','gaps':'Aucune preuve documentaire de demande.'})),
          self.act('finish',text='Audit borné'),self.act('finish',text='Aucun lancement')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            v=actions.pop(0)
            self.assertIn(v['action'],body['text']['format']['schema']['properties']['action']['enum'])
            self.assertIn('DOSSIER COMMERCIAL',body['input'])
            self.assertNotIn('fake-brave',body['input'])
            if v['action']=='commercial_economics':self.assertIn('"price_cents": 10000',body['input'])
            return self.reply(v)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req,patch.object(m,'fetch_page',side_effect=AssertionError('No network')):
            a.worker(s,cid)
        self.assertEqual(actions,[])
        self.assertEqual(req.call_count,12)
        with s.db() as c:
            state=a.status(c);self.assertEqual(state['state'],'terminé',state)
            self.assertEqual(state['scope'],'commercial')
            self.assertEqual(state['missions'][0]['kind'],'commercial')
            offer=co.project_status(c,old)['offer']
            self.assertEqual(offer['state'],'preparation_incomplete')
            self.assertEqual(offer['economics']['result']['monthly_result_cents'],44000)
            self.assertEqual(offer['economics']['result']['adverse_monthly_result_cents'],12000)
            self.assertEqual(offer['economics']['result']['breakeven_units'],2)
            self.assertFalse(offer['external_authorized']);self.assertEqual(offer['sales'],0)
            self.assertEqual(offer['observations'],0);self.assertEqual(offer['commercial_spend_cents'],0)
            self.assertIsNone(co.project_status(c,new)['offer'])
            self.assertEqual(s.campaign_audit(c,self.cfg,cid)['commercial'][0]['offer']['id'],offer['id'])
            self.assertEqual(len(p.status(c)['projects']),2)
            self.assertEqual(state['searches'],0)

    def test_exact_sources_scope_and_future_gate(self):
        *_,old,new=self.historical();cid=self.prepare(old,search_cap=2)
        with s.db() as c:
            mid=m.create(s,c,'Préparation','cloud',a._campaign(c,cid)['source'])
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'commercial')",(cid,mid))
            p.attach(c,mid,old,'test')
            orion={'mission':mid,'agent':'ORION'};hermes={'mission':mid,'agent':'HERMES'}
            midas={'mission':mid,'agent':'MIDAS'};sentinel={'mission':mid,'agent':'SENTINEL'}
            ids=[]
            for domain,kind,quote in [('buyer.example','buyer_problem','Les erreurs coûtent du temps.'),('vendor.example','competitor_price','Forfait annoncé de 100 EUR.')]:
                url='https://'+domain+'/test'
                page=c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,?,'reçue',?)",(mid,url,json.dumps({'url':url,'texte':quote+' '+('Texte documentaire synthétique de test uniquement. '*4),'date':'2026-11-25'}))).lastrowid
                spec={'kind':kind,'quote':quote,'interpretation':'Indice documentaire seulement.'}
                with self.assertRaises(ValueError):co.execute(c,orion,'commercial_signal',str(page),json.dumps({**spec,'quote':'Citation inventée absente.'}),'')
                with self.assertRaises(ValueError):co.execute(c,hermes,'commercial_signal',str(page),json.dumps(spec),'')
                ids.append(co.execute(c,orion,'commercial_signal',str(page),json.dumps(spec),'')['signal'])
            with self.assertRaises(ValueError):co.execute(c,hermes,'commercial_offer','',json.dumps({**PLAN,'signal_ids':[999]}),'')
            oid=co.execute(c,hermes,'commercial_offer','',json.dumps({**PLAN,'signal_ids':ids}),'')['offer']
            with self.assertRaises(ValueError):co.execute(c,sentinel,'commercial_review',str(oid),json.dumps({'verdict':'propose_future_test','gaps':'Avis indépendant limité.'}),'')
            co.execute(c,midas,'commercial_economics',str(oid),json.dumps(ECO),'')
            co.execute(c,sentinel,'commercial_review',str(oid),json.dumps({'verdict':'propose_future_test','gaps':'Vérifier conformité avant action.'}),'')
            self.assertEqual(co.project_status(c,old,mid)['offer']['state'],'preparation_incomplete')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            self.assertEqual(co.project_status(c,old)['offer']['state'],'proposition_a_examiner')
            self.assertFalse(co.project_status(c,old)['offer']['external_authorized'])
            c.execute("UPDATE fetched SET content='{}' WHERE mission=?",(mid,))
            offer=co.project_status(c,old)['offer']
            self.assertEqual(offer['state'],'preparation_incomplete')
            self.assertEqual(offer['invalid_signal_ids'],ids)
            self.assertEqual(co.project_status(c,new)['signals'],[])
            with self.assertRaises(ValueError):co.execute(c,hermes,'commercial_offer','',json.dumps(PLAN),'')

    def test_reject_unapproved_modes_and_tools(self):
        *_,old,new=self.historical()
        flags=dict.fromkeys(a.FLAGS,True)
        with self.assertRaises(ValueError):self.start(project=old,commercial=True,max_missions=1,permissions=flags)
        flags['production']=False
        with self.assertRaises(ValueError):self.start(project=old,commercial=True,max_missions=2,permissions=flags)
        with self.assertRaises(ValueError):self.start(project=old,commercial=True,max_missions=1,permissions=flags,connector_cap=1)
        with s.db() as c:
            mid=m.create(s,c,'Manuelle','cloud')
            self.assertNotIn('commercial_offer',a.permitted(c,mid,'HERMES',m.PERMS['HERMES'])[0])
            with self.assertRaises(ValueError):co.execute(c,{'mission':mid,'agent':'HERMES'},'commercial_offer','',json.dumps(PLAN),'')
