import hashlib
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from wsgiref.simple_server import make_server
import public_channel as ch
import public_channel_http as http

class PublicChannelHTTPTests(unittest.TestCase):
    def test_real_loopback_signed_grants_and_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            key=b't'*32
            t=1800000000
            pid='a'*32
            auth='Bearer '+ch.sign(key,'admin-bearer-v1',{'service':'test-only'})
            app=http.application(str(Path(tmp)/'isolated.sqlite3'),key,lambda:t)
            server=make_server('127.0.0.1',0,app,handler_class=http.QuietHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def call(path,body=None,headers=None):
                with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=headers or {})) as r:
                    return r.read().decode(),dict(r.headers)
            def admin(path,payload,domain=None,authorized=True):
                body=payload if domain is None else {'payload':payload,'signature':ch.sign(key,domain,payload)}
                headers={'Content-Type':'application/json'}
                if authorized:headers['Authorization']=auth
                return json.loads(call('/admin/'+path,json.dumps(body).encode(),headers)[0])
            def reject(fn,status):
                with self.assertRaises(urllib.error.HTTPError) as error:fn()
                self.assertEqual(error.exception.code,status)
            try:
                self.assertFalse(json.loads(call('/health')[0])['live_enabled'])
                m={'id':pid,'mode':'test','snapshot':'b'*64,'offer':5,'title':'<script>unsafe</script>',
                   'description':'Fictif','limitations':'Aucune vente','price_cents':4900,'starts':t,'expires':t+600}
                reject(lambda:admin('publish',m,'publication-v1',False),403)
                admin('publish',m,'publication-v1')
                route='/p/'+pid
                page,headers=call(route)
                self.assertIn('&lt;script&gt;',page)
                self.assertNotIn('<form',page)
                self.assertIn('no-store',headers['Cache-Control'])
                g={'page':pid,'snapshot':m['snapshot'],'publication_hash':hashlib.sha256(ch.canonical(m).encode()).hexdigest(),
                   'mode':'test','starts':t,'expires':t+300,'quota':2,'notice':ch.NOTICE_VERSION}
                admin('collect',g,'collection-v1')
                page,headers=call(route)
                token=re.search('name="token" value="([^"]+)"',page).group(1)
                cookie=headers['Set-Cookie'].split(';')[0]
                body={'token':token,'kind':'demo_request','segment':'yes','consent':'yes'}
                h={'Content-Type':'application/x-www-form-urlencoded','Cookie':cookie}
                def submit(b,headers=h):return call(route,urllib.parse.urlencode(b).encode(),headers)
                reject(lambda:submit({**body,'consent':'no'}),400)
                reject(lambda:submit(body,{'Content-Type':h['Content-Type']}),400)
                result,_=submit(body)
                reject(lambda:submit(body),400)
                reject(lambda:admin('export',{'page':pid},authorized=False),403)
                batch=admin('export',{'page':pid})
                ch.check(key,'export-v1',batch['payload'],batch['signature'])
                self.assertEqual(len(batch['payload']['signals']),1)
                self.assertEqual(batch['payload']['paid_orders'],0)
                event=re.search('name="id" value="([^"]+)"',result).group(1)
                deletion=re.search('name="token" value="([^"]+)"',result).group(1)
                removed=json.loads(call('/withdraw',urllib.parse.urlencode({'id':event,'token':deletion}).encode(),
                    {'Content-Type':h['Content-Type']})[0])
                self.assertTrue(removed['withdrawn'])
                self.assertEqual(admin('export',{'page':pid})['payload']['signals'],[])
                admin('revoke',{'page':pid,'scope':'publication'},'revocation-v1')
                reject(lambda:call(route),400)
            finally:
                server.shutdown();server.server_close();thread.join()
