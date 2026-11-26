import unittest, json, tempfile, threading, urllib.request
from pathlib import Path
from unittest.mock import patch
import serveur as s

class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.p=patch.object(s,'DB',Path(self.tmp.name)/'test.db'); self.p.start(); s.init()
        self.cfg={'key':'fake','brave':'','budget':2000000,'limit':10,'models':s.DEFAULT}
        with s.db() as c: self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('test','cloud','en cours')").lastrowid
    def tearDown(self): self.p.stop(); self.tmp.cleanup()
    def response(self,step):
        return {'status':'completed','usage':{'input_tokens':500,'output_tokens':1000,'output_tokens_details':{'reasoning_tokens':400}},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(s.MOCK[step])}]}]}
    def incomplete(self,reason='max_output_tokens'):
        return {'status':'incomplete','incomplete_details':{'reason':reason},'usage':{'input_tokens':500,'output_tokens':8192,'output_tokens_details':{'reasoning_tokens':8000}}}
    def seed(self):
        with s.db() as c:
            c.execute('INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,?,?,?,?)',(self.mid,0,'ATLAS',json.dumps(s.MOCK[0]),'[]'))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?, 'gpt-6.2-sol',10000,7000,'mesuré')",(self.mid,))
    def test_resume_and_retry(self):
        self.seed()
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=[self.incomplete(),*[self.response(i) for i in range(1,5)]]) as r:
            s.run(self.mid)
            self.assertEqual(r.call_count,5)
            self.assertEqual([x.args[2]['max_output_tokens'] for x in r.call_args_list],[8192,16384,8192,8192,8192])
            self.assertEqual(r.call_args_list[0].args[2]['model'],s.DEFAULT['ORION'])
        with s.db() as c:
            self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'terminée')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],5)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT diagnostic FROM ledger WHERE id=2').fetchone()[0],'incomplete / max_output_tokens')
            self.assertEqual(c.execute('SELECT reasoning_tokens FROM ledger WHERE id=2').fetchone()[0],8000)
            self.assertEqual(c.execute('SELECT actual FROM ledger WHERE id=1').fetchone()[0],7000)
    def test_no_retry_on_filter(self):
        self.seed()
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',return_value=self.incomplete('content_filter')) as r:s.run(self.mid);self.assertEqual(r.call_count,1)
        with s.db() as c:self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'bloquée');self.assertIn('content_filter',c.execute('SELECT error FROM missions').fetchone()[0])
    def test_no_retry_on_refusal(self):
        self.seed();v=self.response(1);v['output'][0]['content']=[{'type':'refusal','refusal':'No'}]
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',return_value=v) as r:s.run(self.mid);self.assertEqual(r.call_count,1)
        with s.db() as c:self.assertIn('refusal',c.execute('SELECT error FROM missions').fetchone()[0])
    def test_retry_budget_and_stop(self):
        self.seed();cfg={**self.cfg,'budget':18000}
        with patch.object(s,'config',return_value=cfg),patch.object(s,'request',return_value=self.incomplete()) as r:s.run(self.mid);self.assertEqual(r.call_count,1)
        with s.db() as c:self.assertIn('Budget',c.execute('SELECT error FROM missions').fetchone()[0]);self.assertLessEqual(s.used(c),cfg['budget'])
    def test_reuse_sources(self):
        self.seed();data=[{'titre':'T','url':'https://example.com','extrait':'D'}]
        with s.db() as c:c.execute("INSERT INTO searches(mission,query,status,result) VALUES(?,'q','reçue',?)",(self.mid,json.dumps(data)))
        with patch.object(s,'config',return_value={**self.cfg,'brave':'fake'}),patch.object(s,'search') as search,patch.object(s,'request',side_effect=[self.response(i) for i in range(1,5)]) as r:
            s.run(self.mid);search.assert_not_called();self.assertIn('https://example.com',r.call_args_list[0].args[2]['input'])
        with s.db() as c:self.assertEqual(json.loads(c.execute('SELECT sources FROM reports WHERE step=1').fetchone()[0]),data)
    def test_http_resume(self):
        self.seed()
        with s.db() as c:c.execute("UPDATE missions SET state='bloquée'")
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler); port=server.server_address[1]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(s,'PORT',port),patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=[self.response(i) for i in range(1,5)]) as r:
                req=urllib.request.Request(f'http://127.0.0.1:{port}/api/resume',data=json.dumps({'id':self.mid,'confirm':True}).encode(),headers={'Content-Type':'application/json','X-Session':s.SESSION})
                with urllib.request.urlopen(req) as res:self.assertEqual(json.load(res)['id'],self.mid)
                import time
                for _ in range(100):
                    with s.db() as c:state=c.execute('SELECT state FROM missions').fetchone()[0]
                    if state!='en cours':break
                    time.sleep(.02)
                self.assertEqual(state,'terminée');self.assertEqual(r.call_count,4)
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
