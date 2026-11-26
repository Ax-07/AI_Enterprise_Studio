"""D06.2: commands via the actual HTTP dispatcher and isolated TEST channel."""
import http.client
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from wsgiref.simple_server import make_server
import serveur as s
import campus_commands as cmd
import campus_tools as tools
import business as b
import acquisition_sync as sync
import acquisition as ac
import public_channel_http as channel_http
import test_business as tb

class CommercialCommandTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def test_contract(self):
        base={'action':'test_publish','confirm':True,'draft':1,'snapshot_sha256':'a'*64,'duration_seconds':1800}
        self.assertEqual(cmd.translate(base)[0],'/api/acquisition/test_publish')
        for body in [{**base,'mode':'live'},{**base,'duration_seconds':1801},{**base,'draft':True},{**base,'snapshot_sha256':'bad'},{**base,'confirm':False},
            {'action':'test_collect','confirm':True,'page':'a'*32,'quota':11,'duration_seconds':60},
            {'action':'business_receipt','confirm':True,'id':1},{'action':'youtube_publish','confirm':True,'id':1}]:
            with self.assertRaises(ValueError):cmd.translate(body)

    def test_local_channel_and_revocation(self):
        oid,_,_=self.fixture()
        offer=next(x for x in tools.read(s.DB,'business',{})['rows'] if x['kind']=='offer' and x['id']==oid)
        self.assertTrue(offer['draft_eligible'])
        with s.db() as db:
            expected=b.digest(b.frozen(ac._offer(db,oid)))
        self.assertEqual(offer['snapshot_sha256'],expected,'Le snapshot campus doit être identique au snapshot métier')
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AES_CHANNEL_TEST_KEY_HEX':(b'x'*32).hex()}),patch.object(sync.acquisition_runtime,'managed',return_value=False),patch.object(s,'request',side_effect=AssertionError('Paid provider forbidden')) as provider:
            service=make_server('127.0.0.1',0,channel_http.application(str(Path(d)/'channel.db'),b'x'*32,b.now),handler_class=channel_http.QuietHandler)
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            threads=[threading.Thread(target=x.serve_forever,daemon=True) for x in (service,server)]
            for t in threads:t.start()
            headers={'Origin':base,'Content-Type':'application/json','X-Campus-Command':s.CAMPUS_COMMAND_SESSION}
            def post(action,code=200,header=None,**body):
                req=urllib.request.Request(base+'/campus/command',data=json.dumps({'action':action,'confirm':True,**body}).encode(),headers=headers if header is None else header)
                if code!=200:
                    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
                    self.assertEqual(e.exception.code,code);return
                try:
                    with urllib.request.urlopen(req) as r:return json.load(r)
                except urllib.error.HTTPError as e:
                    self.fail(f'{action}: HTTP {e.code}: {e.read().decode(errors="replace")}')
            original=http.client.HTTPConnection
            admin=sync.request_admin
            def local_connection(host,port=None,timeout=None,**kwargs):
                if host!='127.0.0.1' or port!=8765:raise AssertionError('Unexpected admin transport')
                return original(host,service.server_port,timeout=timeout,**kwargs)
            def admin_local(*args,**kwargs):
                # Only redirect the actual TEST admin transport, not the client of the enterprise API.
                with patch.object(sync.http.client,'HTTPConnection',side_effect=local_connection):
                    return admin(*args,**kwargs)
            try:
                with patch.object(s,'PORT',port),patch.object(s,'config',return_value=self.cfg),patch.object(sync,'request_admin',side_effect=admin_local):
                    snap=offer['snapshot_sha256']
                    post('draft_prepare',code=403,header={**headers,'X-Campus-Command':s.CAMPUS_READ_SESSION},offer=oid,snapshot_sha256=snap)
                    post('draft_prepare',code=400,offer=oid,snapshot_sha256='0'*64)
                    did=post('draft_prepare',offer=oid,snapshot_sha256=snap)['id']
                    self.assertEqual(post('draft_prepare',offer=oid,snapshot_sha256=snap)['id'],did)
                    pub=post('test_publish',draft=did,snapshot_sha256=snap,duration_seconds=600)
                    self.assertEqual(pub['state'],'published')
                    page=pub['page']
                    post('test_publish',code=400,draft=did,snapshot_sha256=snap,duration_seconds=600)
                    self.assertEqual(post('test_collect',page=page,quota=10,duration_seconds=60)['state'],'collecting')
                    post('test_sync',page=page)
                    self.assertEqual(post('test_stop',page=page)['state'],'revoked')
                    post('draft_revoke',draft=did)
                    post('test_publish',code=400,draft=did,snapshot_sha256=snap,duration_seconds=600)
                    with s.db() as db:
                        self.assertIsNotNone(db.execute('SELECT revoked FROM acquisition_drafts WHERE id=?',(did,)).fetchone()[0])
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM business_receipts').fetchone()[0],0)
                        self.assertEqual(s.used(db),10000)
                    provider.assert_not_called()
            finally:
                for x in (service,server):x.shutdown();x.server_close()
                for t in threads:t.join()
