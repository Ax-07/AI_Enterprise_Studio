import json,os,unittest,threading,http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch,MagicMock
import serveur as s,moteur as m,autopilot as a,connectors as x,n8n_bridge as n
import test_autopilot

TOKEN='T'*43

class N8nTests(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    def configure(self,cap=n.METRICS,**kw):
        with s.db() as c:x.set_policy(c,{'capability':cap,'enabled':True,'agents':['ORION'],'max_calls':20,'budget':'0',**kw})
    def result(self,cap,value,rid):
        return {'request_id':rid,'execution_id':'123','result':n.expected(cap,value),'protocol':n.PROTOCOL}
    def test_contracts_reject_arbitrary_payloads(self):
        self.assertEqual(n.validate(n.HEALTH,' { } '),'{}')
        self.assertEqual(n.validate(n.METRICS,'{"values": [10, -3, 7]}'),'{"values":[10,-3,7]}')
        for text in ('{"values":[]}','{"values":[true]}','{"values":[1.5]}','{"values":[100000001]}','{"values":[NaN]}','{"values":[1],"url":"http://x"}','{"values":[1],"values":[2]}','[1,2]','{"values":['+','.join(['1']*101)+']}'):
            with self.assertRaises(ValueError):n.validate(n.METRICS,text)
        with self.assertRaises(ValueError):n.validate(n.HEALTH,'{"secret":"x"}')
        with self.assertRaises(ValueError):x.validate_input('n8n.workflow','{}')
    def test_configuration_default_deny_no_secret(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':''}):
            with self.assertRaises(ValueError):self.configure()
            with s.db() as c:self.assertFalse(next(v for v in x.status(c)['capabilities'] if v['id']==n.METRICS)['available'])
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}):
            self.configure()
            with s.db() as c:
                data=x.status(c)
                self.assertTrue(next(v for v in data['capabilities'] if v['id']==n.METRICS)['available'])
                self.assertNotIn(TOKEN,json.dumps(data))
        with patch.dict(os.environ,{'AES_N8N_TOKEN':''}),patch.object(n,'call') as call:
            with self.assertRaises(ValueError):x.invoke(s,n.METRICS,'{"values":[1]}')
            call.assert_not_called()
    def test_real_loopback_transport_contract_auth_and_projection(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path,self.headers.get('X-AES-Token'),body))
                r={'protocol':n.PROTOCOL,'request_id':body['request_id'],'execution_id':'456','result':n.expected(n.METRICS,json.dumps(body['input']))}
                raw=json.dumps(r).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        original=http.client.HTTPConnection
        def local(host,port,timeout):
            self.assertEqual((host,port),('127.0.0.1',5678))
            return original(host,server.server_address[1],timeout=timeout)
        try:
            with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}),patch.object(n.http.client,'HTTPConnection',side_effect=local):
                self.configure()
                r=x.invoke(s,n.METRICS,'{"values":[10,-3,7]}')
                self.assertEqual(r['status'],'received')
                self.assertEqual(r['data']['result'],{'count':3,'sum':14,'min':-3,'max':10})
                self.assertEqual(requests[0][:2],('/webhook/aes-v1-metrics',TOKEN))
                self.assertNotIn(TOKEN,json.dumps(requests[0][2]))
                self.assertEqual(requests[0][2]['request_id'],r['data']['request_id'])
                with s.db() as c:
                    d=x.status(c);self.assertNotIn(TOKEN,json.dumps(d))
                    self.assertEqual(d['runs'][0]['execution_id'],'456')
                    self.assertEqual(json.loads(d['runs'][0]['workflow_result'])['result']['sum'],14)
        finally:server.shutdown();server.server_close();thread.join()
    def test_invalid_responses_refused(self):
        rid='a'*32;value='{"values":[1]}'
        valid={'protocol':n.PROTOCOL,'request_id':rid,'execution_id':'123','result':{'count':1,'sum':1,'min':1,'max':1}}
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}),patch.object(n.http.client,'HTTPConnection') as connection:
            resp=MagicMock(status=200);connection.return_value.getresponse.return_value=resp
            for invalid in ({**valid,'request_id':'b'*32},{**valid,'execution_id':TOKEN},{**valid,'result':{'count':1,'sum':9,'min':1,'max':1}},{**valid,'token':TOKEN},{**valid,'result':{'count':True,'sum':1,'min':1,'max':1}}):
                resp.read.return_value=json.dumps(invalid).encode()
                with self.assertRaises(n.Unconfirmed):n.call(n.METRICS,value,rid)
            resp.status=302
            with self.assertRaises(n.Unconfirmed):n.call(n.METRICS,value,rid)
            resp.status=200;resp.read.return_value=b'x'*(n.MAX_BYTES+1)
            with self.assertRaises(n.Unconfirmed):n.call(n.METRICS,value,rid)
    def test_agent_workflow_in_real_engine(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}):
            self.configure()
            cid=self.start(project='explore',connector_cap=1,connector_budget='0')
            actions=[self.act('delegate','ORION','Calcul numérique de démonstration','Résultat'),self.act('connector',n.METRICS,'{"values":[10,-3,7]}'),self.act('finish',text='Calcul vérifié'),self.act('finish',text='Terminé')]
            def fake(url,headers,body=None):
                action=actions.pop(0);enum=body['text']['format']['schema']['properties']['action']['enum']
                self.assertNotIn(TOKEN,json.dumps(body))
                if action['action']=='connector':
                    self.assertIn('connector',enum);self.assertIn(n.METRICS,body['input'])
                else:self.assertNotIn('connector',enum)
                return self.reply(action)
            with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req,patch.object(n,'call',side_effect=self.result) as call:
                a.worker(s,cid);call.assert_called_once();self.assertEqual(req.call_count,4)
            with s.db() as c:
                self.assertEqual(a.status(c)['state'],'terminé')
                self.assertEqual(a.status(c)['connectors']['calls'],1)
                self.assertEqual(x.status(c)['runs'][0]['actor'],'ORION')
                self.assertEqual(c.execute("SELECT COUNT(*) FROM events WHERE action='connector'").fetchone()[0],1)
    def test_uncertain_execution_no_retry_same_mission_and_quota(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}):
            self.configure()
            cid=self.start(project='explore',connector_cap=2)
            with s.db() as c:
                mid=m.create(s,c,'Calcul','cloud');c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid));tid=m.add_task(c,mid,'ORION','Calcul')
            with patch.object(n,'call',side_effect=n.Unconfirmed('HTTP 504')) as call:
                r=x.invoke(s,n.METRICS,'{"values":[1,2]}',mid,tid,'ORION')
                self.assertEqual(r['status'],'unknown');self.assertEqual(r['diagnostic'],'HTTP 504')
                with self.assertRaises(ValueError):x.invoke(s,n.METRICS,'{ "values": [1, 2] }',mid,tid,'ORION')
                call.assert_called_once()
            with s.db() as c:
                self.assertEqual(x.campaign_status(c,cid)['calls'],1)
                run=x.status(c)['runs'][0]
                self.assertEqual(run['state'],'unknown');self.assertEqual(len(run['request_id']),32)
                self.assertIsNone(run['execution_id'])
                c.execute("UPDATE connector_runs SET state='reserved' WHERE id=?",(run['id'],))
                x.init(c)
                self.assertEqual(x.status(c)['runs'][0]['state'],'unknown')
    def test_template_files_no_credentials_and_fixed_nodes(self):
        for cap,file in [(n.HEALTH,'aes_health.json'),(n.METRICS,'aes_metrics.json')]:
            f=json.loads((s.ROOT/'n8n'/file).read_text(encoding='utf8'))
            self.assertFalse(f['active'])
            self.assertEqual([a['type'] for a in f['nodes']],['n8n-nodes-base.webhook','n8n-nodes-base.code'])
            self.assertEqual(f['nodes'][0]['parameters']['authentication'],'headerAuth')
            self.assertEqual('/webhook/'+f['nodes'][0]['parameters']['path'],n.PATHS[cap])
            self.assertNotIn('credentials',f['nodes'][0])
            self.assertEqual(f['settings']['saveDataSuccessExecution'],'none')
