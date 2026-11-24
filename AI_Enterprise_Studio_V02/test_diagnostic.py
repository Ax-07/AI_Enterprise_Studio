import json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
import serveur as s

class Diagnostic(unittest.TestCase):
    def test_free_routes_and_version(self):
        with tempfile.TemporaryDirectory() as d, patch.object(s,'DB',Path(d)/'db'), patch.object(s,'request',side_effect=AssertionError('No provider calls')) as req:
            s.init()
            srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=srv.server_address[1]; t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
            try:
                with patch.object(s,'PORT',port):
                    base=f'http://127.0.0.1:{port}'
                    with urllib.request.urlopen(base+'/api/health') as r:
                        self.assertEqual(r.headers['X-Enterprise-Version'],'0.3.3');self.assertFalse(json.load(r)['paid_call'])
                    with urllib.request.urlopen(urllib.request.Request(base+'/api/status',headers={'X-Session':s.SESSION})) as r:
                        v=json.load(r);self.assertEqual(v['version'],'0.3.3');self.assertTrue(v['resume_supported'])
                    with urllib.request.urlopen(base+'/?refresh=1') as r:
                        html=r.read().decode();self.assertIn('V0.3.3',html);self.assertIn(s.SESSION,html)
                    with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(base+'/api/unknown')
                    self.assertEqual(ctx.exception.code,404); self.assertIn('GET /api/unknown',json.load(ctx.exception)['error'])
                    with s.db() as c:self.assertEqual(s.used(c),0)
                    req.assert_not_called()
            finally:srv.shutdown();srv.server_close();t.join()
