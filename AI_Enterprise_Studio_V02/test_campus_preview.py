import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from pathlib import Path
import campus_preview as preview
import serveur as s

class CampusPreviewTests(unittest.TestCase):
    def test_assets_and_separation(self):
        root=Path(__file__).resolve().parent
        manifest=json.loads((root/'interface'/'manifest.json').read_text(encoding='utf8'))
        self.assertEqual(manifest['design'],'22.6')
        self.assertFalse(manifest['api'])
        self.assertEqual(len(set(manifest['assets'])),35)
        html,typ=preview.read(root,'/campus')
        self.assertIn('text/html',typ)
        self.assertIn(b'APER',html)
        self.assertNotIn(b'__SESSION__',html)
        self.assertNotIn(b'data:image/webp;base64,',html)
        js,typ=preview.read(root,'/campus/design.js')
        self.assertNotIn(b'data:image/webp;base64,',js)
        self.assertNotIn(b'/api/',js)
        for asset in manifest['assets']:
            data,typ=preview.read(root,'/campus/assets/'+asset)
            self.assertEqual(typ,'image/webp')
            self.assertEqual(data[:4],b'RIFF')
            self.assertEqual(data[8:12],b'WEBP')
            self.assertIn(('/campus/assets/'+asset).encode(),js)
        for path in ('/campus/manifest.json','/campus/assets/../index.html','/campus/assets/unknown.webp',
                     '/campus/../serveur.py','/campus/assets/%2e%2e'):
            self.assertIsNone(preview.read(root,path))

    def test_http_preview_no_session_or_database(self):
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        port=server.server_address[1]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(port)
        try:
            with patch.object(s,'PORT',port),patch.object(s,'status',side_effect=AssertionError('No database status')):
                with urllib.request.urlopen(base+'/campus/') as r:
                    self.assertEqual(r.status,200)
                    self.assertIn("connect-src 'none'",r.headers['Content-Security-Policy'])
                    self.assertIn("img-src 'self'",r.headers['Content-Security-Policy'])
                    self.assertNotIn(s.SESSION.encode(),r.read())
                with urllib.request.urlopen(base+'/campus/assets/campus_2_0.webp') as r:
                    self.assertEqual(r.headers['Content-Type'],'image/webp')
                with urllib.request.urlopen(base+'/') as r:
                    self.assertIn(b'/campus/',r.read())
                for url in ('/campus/manifest.json','/campus/assets/unknown.webp'):
                    with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(base+url)
                    self.assertEqual(err.exception.code,404)
                req=urllib.request.Request(base+'/api/start',data=b'{}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                self.assertEqual(err.exception.code,403)
        finally:server.shutdown();server.server_close();thread.join()
