import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s, moteur as m, autopilot as a

class AutopilotTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        pp=patch.object(s,'DB',Path(t.name)/'db');pp.start();self.addCleanup(pp.stop)
        s.init();self.cfg={**s.config(),'key':'fake','brave':'fake-brave','budget':2000000,'mission_budget':750000,'call_limit':40,'turn_limit':10}
        self.body={'goal':'Diversifier les activités','budget':'1.00','max_missions':3,'permissions':dict.fromkeys(a.FLAGS,True),'search_cap':0,'confirm':True}
    def start(self,**kwargs):
        with s.db() as c:return a.start(c,{**self.body,**kwargs},self.cfg)
    def state(self):
        with s.db() as c:return a.status(c)
    def act(self,action,target='',text='',detail=''):
        return dict(action=action,target=target,text=text,detail=detail)
    def reply(self,v):
        return {'status':'completed','usage':{'input_tokens':100,'output_tokens':40},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(v)}]}]}
    def test_three_missions_real_engine_mock_provider(self):
        cid=self.start()
        spec=json.dumps({'checks':[{'name':'Nombre de lignes','op':'row_count','expected':1}]})
        actions=[
          self.act('delegate','ORION','Étude ciblée','Hypothèse'),
          self.act('opportunity','Kit de suivi','Hypothèse non validée','Test de demande'),
          self.act('finish',text='Étude avec limites'),
          self.act('finish',text='Opportunité enregistrée'),
          self.act('delegate','NEXUS','Créer CSV','Interne'),
          self.act('write_file','kit.csv','a,b\n1,2\n','Exemple interne'),
          self.act('finish',text='Fichier créé'),
          self.act('finish',text='Production interne'),
          self.act('delegate','SENTINEL','Tester la référence','Une assertion'),
          self.act('test_file','ref:1',spec),
          self.act('finish',text='Test borné'),
          self.act('finish',text='Audit limité')
        ]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            value=actions.pop(0)
            self.assertIn(value['action'],body['text']['format']['schema']['properties']['action']['enum'])
            return self.reply(value)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req:
            a.worker(s,cid)
        self.assertEqual(actions,[])
        self.assertEqual(req.call_count,12)
        p=self.state()
        self.assertEqual(p['state'],'terminé')
        self.assertEqual([x['kind'] for x in p['missions']],['opportunity','create','functional'])
        self.assertEqual([x['state'] for x in p['missions']],['terminée']*3)
        self.assertGreater(p['spent'],0);self.assertLess(p['spent'],p['budget'])
        with s.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],12)
            proof=json.loads(c.execute('SELECT result FROM verification_results').fetchone()[0])
            self.assertEqual(proof['status'],'passed')
    def test_envelope_before_network(self):
        cid=self.start(budget='0.01')
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=AssertionError('No network')) as req:
            a.worker(s,cid);req.assert_not_called()
        p=self.state()
        self.assertEqual(p['state'],'bloqué')
        self.assertIn('Enveloppe Autopilote',p['reason'])
        self.assertEqual(p['spent'],0);self.assertEqual(len(p['missions']),1)
    def test_sum_reservations_across_missions(self):
        cid=self.start(budget='0.10')
        with s.db() as c:
            one=m.create(s,c,'Première','cloud');two=m.create(s,c,'Deuxième','cloud')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(one,))
            for mid in (one,two):c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',90000,'à rapprocher')",(one,))
            self.assertEqual(a.costs(c,cid),90000)
            a.reserve(c,two,10000)
            with self.assertRaisesRegex(RuntimeError,'Enveloppe'):a.reserve(c,two,10001)
    def test_permissions_search_and_delegation(self):
        cid=self.start(permissions={'research':True,'production':False,'tests':False,'market':False},search_cap=1)
        with s.db() as c:
            mid=m.create(s,c,'Test','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
            for act,target in [('delegate','NEXUS'),('write_file','x.csv'),('test_file','x.csv')]:
                with self.assertRaises(ValueError):a.guard(c,mid,'ATLAS',act,target,set([act]))
            a.search_allowed(c,mid)
            c.execute("INSERT INTO searches(mission,query,status) VALUES(?,'test','tentée')",(mid,))
            with self.assertRaises(ValueError):a.search_allowed(c,mid)
    def test_stop_restart_resume_no_reset(self):
        cid=self.start()
        with s.db() as c:
            mid=m.create(s,c,'Test','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',5000,'réservé')",(mid,))
            a.stop(c,cid)
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0],'arrêtée')
            with self.assertRaises(RuntimeError):a.reserve(c,mid,1)
            a.resume(c,cid,self.cfg)
        s.init()
        self.assertEqual(self.state()['state'],'interrompu')
        with s.db() as c:a.resume(c,cid,self.cfg)
        self.assertEqual(self.state()['spent'],5000)
        self.assertEqual(len(self.state()['missions']),1)
    def test_missing_proof_stops_without_market(self):
        with s.db() as c:
            mid=m.create(s,c,'Produit','cloud')
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',1,'NEXUS','a,b','test')",(mid,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
        cid=self.start()
        with s.db() as c:
            self.assertEqual(a.choose(c,a._campaign(c,cid))[0],('functional',aid,None))
            mid=m.create(s,c,'Audit','cloud',aid)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'functional',?)",(cid,mid,aid))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            self.assertIsNone(a.choose(c,a._campaign(c,cid))[0])
    def test_validation_and_one_active(self):
        for body in ({'confirm':False},{'budget':'3.00'},{'budget':'NaN'},{'max_missions':0},{'search_cap':11}):
            with self.assertRaises(ValueError):self.start(**body)
        self.start()
        with self.assertRaises(ValueError):self.start()
