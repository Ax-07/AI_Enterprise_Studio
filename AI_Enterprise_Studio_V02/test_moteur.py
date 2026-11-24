import json, tempfile, unittest, threading, urllib.request, time
from pathlib import Path
from unittest.mock import patch
import serveur as s, moteur as m

class Dynamic(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(s,'DB',Path(self.tmp.name)/'db');self.p.start();s.init();self.cfg={**s.config(),'key':'test','brave':'test','budget':2000000,'mission_budget':1000000,'limit':10}
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def make(self,mode='cloud'):
        with s.db() as c:return m.create(s,c,'Étude de test',mode)
    def task(self,mid,agent='ATLAS'):
        with s.db() as c:
            t=c.execute('SELECT * FROM tasks WHERE mission=? AND agent=?',(mid,agent)).fetchone()
            if not t:
                tid=m.add_task(c,mid,agent,'test');t=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
            return dict(t)
    def state(self,mid):
        with s.db() as c:return c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0]
    def act(self,a,target='',text='',detail=''):return dict(action=a,target=target,text=text,detail=detail)
    def response(self,v):return {'status':'completed','usage':{'input_tokens':1200,'output_tokens':400},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(v)}]}]}
    def test_free_demo(self):
        mid=self.make('demo')
        with patch.object(s,'request',side_effect=AssertionError('No network')) as net,patch.object(m,'fetch_page',side_effect=AssertionError('No network')):s.run(mid);net.assert_not_called()
        self.assertEqual(self.state(mid),'terminée')
        with s.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0],5);self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],13);self.assertEqual(c.execute('SELECT count(*) FROM artifacts').fetchone()[0],1);self.assertEqual(s.used(c),0);self.assertEqual(c.execute('SELECT count(*) FROM rewards').fetchone()[0],0)
    def test_real_protocol_mock(self):
        mid=self.make(); acts=[self.act('delegate','ORION','Cherche le marché','Sources'),self.act('search',text='official test'),self.act('read','https://example.com/'),self.act('opportunity','Hypothèse','Produit','Test'),self.act('finish',text='Étude avec limites'),self.act('delegate','NEXUS','Créer fichier','CSV'),self.act('write_file','kit.csv','name,price\nA,12\n'),self.act('finish',text='Brouillon'),self.act('delegate','SENTINEL','Vérifier','CSV'),self.act('check_file','kit.csv'),self.act('finish',text='Contrôle statique'),self.act('finish',text='Décision préliminaire')]
        def respond(url,headers,body=None):
            if 'brave.com' in url:return {'web':{'results':[{'title':'Source','url':'https://example.com/','description':'Extrait'}]}}
            self.assertEqual(body['text']['format']['name'],'action_agent');return self.response(acts.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=respond),patch.object(m,'fetch_page',return_value={'url':'https://example.com/','texte':'Prix indicatif','partiel':False}) as fetch:s.run(mid);fetch.assert_called_once()
        self.assertEqual(self.state(mid),'terminée');self.assertEqual(acts,[])
        with s.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM searches').fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM fetched').fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM reports').fetchone()[0],4);self.assertEqual(c.execute('SELECT SUM(xp) FROM rewards').fetchone()[0],10);self.assertGreater(s.used(c),0)
    def test_approval_http_auto_resume(self):
        mid=self.make();acts=[self.act('delegate','ORION','Étude','Critère'),self.act('request','Étude complémentaire','Lire les sources','0 €, risque faible'),self.act('finish',text='Étude interne terminée'),self.act('finish',text='Conclusion')]
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=lambda *a:self.response(acts.pop(0))) as req:
            s.run(mid);self.assertEqual(self.state(mid),'en attente');self.assertEqual(req.call_count,2)
            with s.db() as c:rid=c.execute('SELECT id FROM requests').fetchone()[0]
            srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);th=threading.Thread(target=srv.serve_forever,daemon=True);th.start();port=srv.server_address[1]
            try:
                with patch.object(s,'PORT',port):
                    url=f'http://127.0.0.1:{port}/api/decision';body=json.dumps({'id':rid,'decision':'étude acceptée','confirm':True}).encode()
                    with urllib.request.urlopen(urllib.request.Request(url,data=body,headers={'X-Session':s.SESSION,'Content-Type':'application/json'})) as r:self.assertEqual(json.load(r)['reprise'],mid)
                    for _ in range(100):
                        if self.state(mid)!='en cours':break
                        time.sleep(.02)
                    self.assertEqual(self.state(mid),'terminée');self.assertEqual(req.call_count,4)
                    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(url,data=body,headers={'X-Session':s.SESSION,'Content-Type':'application/json'}))
                    self.assertEqual(req.call_count,4)
            finally:srv.shutdown();srv.server_close();th.join()
    def test_budget(self):
        mid=self.make()
        with patch.object(s,'config',return_value={**self.cfg,'mission_budget':1}),patch.object(s,'request') as req:s.run(mid);req.assert_not_called()
        self.assertEqual(self.state(mid),'bloquée')
    def test_permissions_and_ssrf(self):
        mid=self.make();t=self.task(mid)
        for a in [self.act('write_file','x.py','print(1)'),self.act('read','https://127.0.0.1/')]:
            with self.assertRaises(ValueError):m.execute(s,t,a,self.cfg,'cloud')
        with self.assertRaises(ValueError):m.fetch_page('http://example.com/')
        with patch.object(m.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):m.fetch_page('https://example.com/')
        with self.assertRaises(ValueError):m.calc('__import__("os")')
        self.assertAlmostEqual(m.calc('19.99-8.23-19.99*0.25'),6.7625)
    def test_files_version_and_validation(self):
        mid=self.make();t=self.task(mid,'NEXUS')
        for n in ('../serveur.py','config.json/xx.py','C:/bad.py'):
            with self.assertRaises(ValueError):m.execute(s,t,self.act('write_file',n,'x=1'),self.cfg,'cloud')
        for content in ('x=1','x=2','x=2'):
            m.execute(s,t,self.act('write_file','test.py',content),self.cfg,'cloud')
        with s.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM artifacts').fetchone()[0],2)
        self.assertFalse(m.check('bad.py','def f(')['valide']);self.assertFalse(m.check('bad.csv','a,b\nc')['valide'])
        self.assertTrue(m.check('ok.json','{"x":1}')['valide'])
    def test_legacy_and_cost_preserved(self):
        with s.db() as c:
            mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('ancienne','cloud','terminée')").lastrowid
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?, 'gpt-6.2-sol',1000,700,'mesuré')",(mid,))
            c.execute("INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,0,'ATLAS','{}','[]')",(mid,))
        s.init()
        with s.db() as c:self.assertEqual(s.used(c),700);self.assertEqual(c.execute('SELECT engine FROM missions WHERE id=?',(mid,)).fetchone()[0],'legacy');self.assertEqual(c.execute('SELECT count(*) FROM reports').fetchone()[0],1)
    def test_search_limits_cache(self):
        mid=self.make();t=self.task(mid,'ORION');cfg={**self.cfg,'mission_search_limit':1}
        with patch.object(s,'request',return_value={'web':{'results':[{'url':'https://example.com/'}]}}) as req:
            m.execute(s,t,self.act('search',text='q'),cfg,'cloud');m.execute(s,t,self.act('search',text='q'),cfg,'cloud');self.assertEqual(req.call_count,1)
            with self.assertRaises(ValueError):m.execute(s,t,self.act('search',text='autre'),cfg,'cloud')
