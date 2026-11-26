import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_commands as commands

class CampusCommandTests(unittest.TestCase):
    def test_closed_contract(self):
        self.assertEqual(commands.translate({'action':'mission_demo','confirm':True,'title':' test '}),('/api/start',{'title':'test','mode':'demo','engine':'dynamic'}))
        for body in [None,{}, {'action':'mission_demo','confirm':True,'title':'test','mode':'cloud'},
            {'action':'mission_demo','confirm':1,'title':'test'},
            {'action':'mission_stop','confirm':True,'id':True},
            {'action':'mission_stop','confirm':True,'id':0},
            {'action':'mission_stop','confirm':True,'id':1,'route':'/api/start'},
            {'action':'campaign_start','confirm':True,'id':1}]:
            with self.assertRaises(ValueError):commands.translate(body)

    def test_http_commands(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(s,'run'):
            s.init()
            srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
            th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
            headers={'Content-Type':'application/json','Origin':base,'X-Campus-Command':s.CAMPUS_COMMAND_SESSION}
            def post(body,h=None,path='/campus/command',code=200):
                req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers if h is None else h)
                if code!=200:
                    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                    self.assertEqual(err.exception.code,code);return
                with urllib.request.urlopen(req) as r:return json.load(r)
            demo={'action':'mission_demo','confirm':True,'title':'Simulation campus'}
            try:
                with patch.object(s,'PORT',port),patch.object(s,'config',return_value={**s.config(),'key':'fake','budget':4000000}):
                    post(demo,{'Content-Type':'application/json','Origin':base,'X-Campus-Session':s.CAMPUS_READ_SESSION},code=403)
                    post(demo,{**headers,'Origin':'https://evil.example'},code=403)
                    post(demo,{**headers,'Sec-Fetch-Site':'cross-site'},code=403)
                    post(demo,{**headers,'Origin':''},code=403)
                    post(demo,{**headers,'Content-Type':'text/plain'},code=403)
                    post(demo,path='/campus/command?x=1',code=403)
                    post({'mode':'cloud','title':'test','confirm':True},path='/api/start',h={**headers,'X-Session':s.CAMPUS_COMMAND_SESSION},code=403)
                    post({**demo,'mode':'cloud'},code=400)
                    post({'action':'campaign_start','confirm':True},code=400)
                    mid=post(demo)['id']
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT mode FROM missions WHERE id=?',(mid,)).fetchone()[0],'demo')
                    post(demo,code=400)
                    post({'action':'mission_stop','confirm':True,'id':mid})
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0],'arrêtée')
                        cid=db.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('test',400000,2,'{}',0,'actif')").lastrowid
                    post({'action':'campaign_stop','confirm':True,'id':cid})
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT state FROM campaigns WHERE id=?',(cid,)).fetchone()[0],'arrêté')
                        pid=db.execute("INSERT INTO enterprise_plans(budget,per_campaign,max_campaigns,search_cap,explore,state) VALUES(1000000,400000,2,0,0,'active')").lastrowid
                    post(demo,code=400)
                    post({'action':'plan_stop','confirm':True,'id':pid})
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT state FROM enterprise_plans WHERE id=?',(pid,)).fetchone()[0],'paused')
                        gid=db.execute("INSERT INTO periodic_grants(cadence,seconds,periods,starts,expires,last_seen,total_budget,period_budget,per_campaign,max_campaigns,total_search,period_search,explore,state) VALUES('daily',86400,2,1,172801,1,2000000,1000000,400000,2,4,2,0,'active')").lastrowid
                    post(demo,code=400)
                    post({'action':'periodic_revoke','confirm':True,'id':gid})
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT state FROM periodic_grants WHERE id=?',(gid,)).fetchone()[0],'revoked')
                        self.assertEqual(s.used(db),0)
                    network.assert_not_called()
            finally:srv.shutdown();srv.server_close();th.join()
