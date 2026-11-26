import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import serveur as s
import preview_campus as p

class PreviewTests(unittest.TestCase):
    def test_read_only_boundary(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            s.init()
            with s.db() as c:
                c.execute("INSERT INTO missions(title,mode,state,engine) VALUES('historical','cloud','terminée','dynamic')")
            before=s.DB.read_bytes()
            server=s.ThreadingHTTPServer(('127.0.0.1',0),p.PreviewHandler)
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                with patch.object(s,'PORT',port),patch.object(s,'request',side_effect=AssertionError('Network forbidden')) as network,patch.object(s,'init',side_effect=AssertionError('No startup migration')),patch.object(s,'status',side_effect=AssertionError('No legacy status')):
                    for path in ('/','/campus/live/?building=ATLAS&floor=OWNER'):
                        with urllib.request.urlopen(base+path) as r:html=r.read()
                        self.assertIn(b'content="preview" name="campus-mode"',html)
                        self.assertIn(s.CAMPUS_READ_SESSION.encode(),html)
                        for token in (s.CAMPUS_COMMAND_SESSION,s.CAMPUS_OWNER_SESSION,s.SESSION):self.assertNotIn(token.encode(),html)
                    request=urllib.request.Request(base+'/campus/live-data',headers={'X-Campus-Session':s.CAMPUS_READ_SESSION})
                    with urllib.request.urlopen(request) as r:self.assertTrue(json.load(r)['read_only'])
                    with urllib.request.urlopen(base+'/api/health') as r:self.assertEqual(json.load(r)['mode'],'preview_read_only')
                    for route in ('/api/status','/api/acquisition_audit'):
                        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(base+route)
                        self.assertEqual(exc.exception.code,403)
                    for route in ('/api/start','/campus/command','/campus/owner-command'):
                        req=urllib.request.Request(base+route,data=b'{}',headers={'Origin':base,'Content-Type':'application/json','X-Session':s.SESSION,'X-Campus-Command':s.CAMPUS_COMMAND_SESSION,'X-Campus-Owner':s.CAMPUS_OWNER_SESSION})
                        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
                        self.assertEqual(exc.exception.code,403)
                    network.assert_not_called()
                    self.assertEqual(s.DB.read_bytes(),before)
            finally:server.shutdown();server.server_close();t.join()
