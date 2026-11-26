"""D05.2: strict owner contracts and real dispatch on a temporary DB."""
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_commands as cmd

class OwnerCommandTests(unittest.TestCase):
    def test_closed_owner_contract(self):
        valid={'action':'plan_start','confirm':True,'budget':'1','per_campaign':'0.4','max_campaigns':2,'search_cap':0,'explore':False}
        self.assertEqual(cmd.owner_translate(valid)[0],'/api/planner/start')
        for body in [{**valid,'extra':True},{**valid,'confirm':1},{**valid,'budget':'NaN'},{**valid,'max_campaigns':True},{**valid,'explore':'true'},{'action':'arbitrary','confirm':True}]:
            with self.assertRaises(ValueError):cmd.owner_translate(body)
        with self.assertRaises(ValueError):cmd.translate(valid)
        self.assertEqual(cmd.owner_translate({'action':'decision','id':1,'decision':'refusée','confirm':True})[0],'/api/decision')

    def test_owner_boundary_and_engine(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(s,'run'),patch.object(s.planner,'worker'),patch.object(s.autopilot,'worker'):
            s.init()
            srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
            th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
            cfg={**s.config(),'key':'fake','brave':'fake','budget':4000000,'limit':10,'mission_search_limit':6}
            headers={'Origin':base,'Content-Type':'application/json','X-Campus-Owner':s.CAMPUS_OWNER_SESSION}
            def post(body,h=None,path='/campus/owner-command',code=200):
                req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers if h is None else h)
                if code!=200:
                    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                    self.assertEqual(err.exception.code,code);return
                with urllib.request.urlopen(req) as r:return json.load(r)
            plan={'action':'plan_start','confirm':True,'budget':'1','per_campaign':'0.4','max_campaigns':2,'search_cap':0,'explore':False}
            try:
                with patch.object(s,'PORT',port),patch.object(s,'config',return_value=cfg):
                    for path,expected in [('/campus/',False),('/campus/live/',False),('/campus/live/?building=ATLAS&floor=OWNER',True)]:
                        with urllib.request.urlopen(base+path) as r:
                            self.assertEqual(s.CAMPUS_OWNER_SESSION.encode() in r.read(),expected)
                    post(plan,{**headers,'X-Campus-Owner':s.CAMPUS_COMMAND_SESSION},code=403)
                    post(plan,{**headers,'Origin':'https://evil.example'},code=403)
                    post(plan,path='/campus/command',h={**headers,'X-Campus-Command':s.CAMPUS_COMMAND_SESSION},code=400)
                    post({**plan,'budget':'5'},code=400)
                    mid=post({'action':'mission_cloud','confirm':True,'title':'Cloud test sans worker'})['id']
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT mode FROM missions WHERE id=?',(mid,)).fetchone()[0],'cloud')
                        db.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
                        rid=db.execute("INSERT INTO requests(mission,body) VALUES(?,'{}')",(mid,)).lastrowid
                    post({'action':'decision','id':rid,'decision':'refusée','confirm':True})
                    with s.db() as db:self.assertEqual(db.execute('SELECT state FROM requests WHERE id=?',(rid,)).fetchone()[0],'refusée')
                    pid=post(plan)['plan']
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT budget FROM enterprise_plans WHERE id=?',(pid,)).fetchone()[0],1000000)
                    post({'action':'mission_cloud','confirm':True,'title':'interdit plan actif'},code=400)
                    post({'action':'plan_stop','id':pid,'confirm':True},path='/campus/command',h={**headers,'X-Campus-Command':s.CAMPUS_COMMAND_SESSION})
                    with s.db() as db:s.planner.abandon(db,pid)
                    period={'action':'periodic_authorize','confirm':True,'cadence':'daily','periods':2,'total_budget':'1','period_budget':'0.5','per_campaign':'0.2','max_campaigns':2,'total_search':0,'period_search':0,'explore':False}
                    gid=post(period)['grant']
                    with s.db() as db:
                        self.assertEqual(db.execute('SELECT total_budget FROM periodic_grants WHERE id=?',(gid,)).fetchone()[0],1000000)
                        self.assertEqual(s.used(db),0)
                    network.assert_not_called()
            finally:srv.shutdown();srv.server_close();th.join()
