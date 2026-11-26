import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import campus_live
import serveur as s

def fixture(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE missions(id INTEGER PRIMARY KEY,title TEXT,mode TEXT,state TEXT,created TEXT);
        CREATE TABLE tasks(id INTEGER PRIMARY KEY,mission INTEGER,agent TEXT,state TEXT,created TEXT,goal TEXT);
        CREATE TABLE events(id INTEGER PRIMARY KEY,mission INTEGER,agent TEXT,action TEXT,ok INTEGER,created TEXT,args TEXT);
        CREATE TABLE artifacts(id INTEGER PRIMARY KEY,mission INTEGER,agent TEXT,name TEXT,version INTEGER,created TEXT,content TEXT);
        CREATE TABLE ledger(actual INTEGER,reserved INTEGER,mission INTEGER,agent TEXT);
        CREATE TABLE reports(id INTEGER PRIMARY KEY,mission INTEGER,agent TEXT,report TEXT,created TEXT);
        CREATE TABLE opportunities(id INTEGER PRIMARY KEY,mission INTEGER,title TEXT,body TEXT,next_test TEXT,status TEXT,created TEXT);
        CREATE TABLE requests(state TEXT,body TEXT);
        INSERT INTO missions VALUES(1,'Mission moteur','cloud','en cours','2026-01-01'),(2,'Mission démo','demo','terminée','2026-01-01');
        INSERT INTO tasks VALUES(1,1,'MNEMOS','en cours','2026-01-01','secret-test'),(2,2,'PROMETHEUS','en cours','2026-01-01','secret-test');
        INSERT INTO events VALUES(1,1,'MNEMOS','indexer',1,'2026-01-01','secret-test');
        INSERT INTO artifacts VALUES(1,2,'NEXUS','Exemple',1,'2026-01-01','secret-test');
        INSERT INTO ledger VALUES(1000,2000,1,'MNEMOS'),(NULL,3000,2,'NEXUS');
        INSERT INTO reports VALUES(1,1,'MNEMOS','{"rapport":"Recherche de marché test"}','2026-01-01');
        INSERT INTO opportunities VALUES(1,1,'Hypothèse test','Analyse','Vérifier','hypothèse','2026-01-01');
        INSERT INTO requests VALUES('en attente','secret-test');
        """)

class CampusLiveTests(unittest.TestCase):
    def test_projection_and_missing_database(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';fixture(path);before=path.read_bytes()
            snap=campus_live.snapshot(path,s.AGENTS,4000000,s.VERSION)
            self.assertEqual(snap['schema'],'aes.campus.read.v1')
            self.assertEqual(len(snap['buildings']),7)
            self.assertEqual(sum(len(b['agents']) for b in snap['buildings']),8)
            core=snap['buildings'][-1]['agents']
            self.assertEqual([a['id'] for a in core],['MNEMOS','PROMETHEUS'])
            self.assertEqual(core[0]['active_tasks_by_mode'],{'cloud':1})
            self.assertEqual(core[1]['active_tasks_by_mode'],{})
            self.assertEqual(snap['budget']['committed_estimate_micro_usd'],4000)
            self.assertEqual(snap['artifacts'][0]['mode'],'demo')
            self.assertEqual(snap['pending_requests'],1)
            self.assertNotIn('secret-test',json.dumps(snap))
            self.assertEqual(path.read_bytes(),before)
            missing=Path(d)/'missing.db'
            with self.assertRaises(sqlite3.OperationalError):campus_live.snapshot(missing,s.AGENTS,0,s.VERSION)
            self.assertFalse(missing.exists())

    def test_http_read_only_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';fixture(path)
            srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
            thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
            def get(url,headers=None):
                return urllib.request.urlopen(urllib.request.Request(base+url,headers=headers or {}))
            def denied(url,headers,code,data=None):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(urllib.request.Request(base+url,headers=headers,data=data))
                self.assertEqual(e.exception.code,code)
            try:
                with patch.object(s,'PORT',port),patch.object(s,'DB',path),patch.object(s,'config',return_value={'budget':4000000}),patch.object(s,'status',side_effect=AssertionError('Full status forbidden')):
                    with get('/campus/live/') as r:
                        html=r.read()
                        self.assertIn(s.CAMPUS_READ_SESSION.encode(),html)
                        self.assertNotIn(s.SESSION.encode(),html)
                        self.assertIn(s.CAMPUS_COMMAND_SESSION.encode(),html)
                        self.assertIn("connect-src 'self'",r.headers['Content-Security-Policy'])
                        self.assertIn('no-store',r.headers['Cache-Control'])
                    with get('/campus/') as r:
                        html=r.read()
                        self.assertNotIn(s.CAMPUS_READ_SESSION.encode(),html)
                        self.assertNotIn(s.CAMPUS_COMMAND_SESSION.encode(),html)
                        self.assertIn("connect-src 'none'",r.headers['Content-Security-Policy'])
                    denied('/campus/live-data',{},403)
                    denied('/campus/live-data',{'X-Session':s.SESSION},403)
                    token={'X-Campus-Session':s.CAMPUS_READ_SESSION}
                    denied('/campus/live-data',{**token,'Origin':'https://evil.example'},403)
                    denied('/campus/live/',{'Sec-Fetch-Site':'cross-site'},403)
                    denied('/api/start',{'X-Session':s.CAMPUS_READ_SESSION,'Content-Type':'application/json'},403,b'{}')
                    with get('/campus/live-data',token) as r:
                        self.assertEqual(json.load(r)['source'],'local_sqlite')
                    denied('/campus/read?tool=files',{},403)
                    denied('/campus/read?tool=files',{'X-Session':s.SESSION},403)
                    denied('/campus/read?tool=files',{**token,'Origin':'https://evil.example'},403)
                    denied('/campus/read?tool=delete',token,400)
                    denied('/campus/read?tool=artifact&id=0',token,400)
                    denied('/campus/read?tool=artifact&id=999',token,404)
                    denied('/campus/read?tool=memory&q=x',token,400)
                    denied('/campus/read?tool=files',token,403,b'{}')
                    for name in ('missions','work','files','finance','opps'):
                        with get('/campus/read?tool='+name,token) as r:
                            result=json.load(r);self.assertTrue(result['read_only']);self.assertTrue(result['rows'])
                    with get('/campus/read?tool=artifact&id=1',token) as r:
                        self.assertEqual(json.load(r)['rows'][0]['content'],'secret-test')
                    with get('/campus/read?tool=memory&q=marche',token) as r:
                        self.assertEqual(json.load(r)['rows'],[])
                    with get('/campus/read?tool=report&id=1',token) as r:
                        self.assertEqual(json.load(r)['rows'][0]['content'],'Recherche de marché test')
                    with patch.object(s,'DB',Path(d)/'missing.db'):
                        denied('/campus/live-data',token,503)
            finally:srv.shutdown();srv.server_close();thread.join()
