import json, threading, unittest, urllib.request, urllib.error
from unittest.mock import patch
import acquisition as ac
import business as b
import serveur as s
import test_business as tb

class AcquisitionTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def body(self,c,oid,**kw):
        o=next(x for x in b.status(c,self.T)['catalog'] if x['offer']==oid)
        return {'confirm':True,'offer':oid,'snapshot_sha256':o['snapshot_sha256'],'language':'fr',**kw}

    def test_migration_deterministic_preview_no_commercial_effect(self):
        oid,aid,pid=self.fixture()
        with patch.object(s,'request',side_effect=AssertionError('No provider')) as req:
            s.init();s.init()
            with s.db() as c:
                old=b.status(c,self.T)
                body=self.body(c,oid)
                did=ac.prepare(c,body,self.T)
                self.assertEqual(ac.prepare(c,body,self.T+1),did)
                payload=ac.preview(c,did)
                self.assertEqual(payload['artifact_sha256'],old['catalog'][0]['artifact_sha256'])
                self.assertEqual(payload['snapshot_sha256'],body['snapshot_sha256'])
                self.assertEqual(payload['classification'],'internal_draft')
                self.assertEqual(payload['risks'],old['catalog'][0]['plan']['risks'].strip())
                self.assertIn('NON PUBLIÉ',payload['html'])
                self.assertIn('button disabled',payload['html'])
                self.assertIn("form-action 'none'",payload['html'])
                self.assertNotIn('<form',payload['html'])
                self.assertNotIn('<script',payload['html'])
                self.assertEqual(payload['demo']['paid_orders'],0)
                self.assertEqual(payload['demo']['real_observations'],0)
                self.assertEqual(old,b.status(c,self.T))
                st=ac.status(c)
                self.assertEqual(len(st['drafts']),1)
                self.assertEqual(len(st['events']),1)
                for k in ('publication_authorized','collection_authorized','channel_ready'):
                    self.assertFalse(st[k])
                self.assertEqual(st['external_spend_cents'],0)
                self.assertEqual(st['prospects'],0)
                self.assertEqual(s.used(c),10000)
            req.assert_not_called()

    def test_invalid_fields_stale_reference_and_revocation(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            for kw in ({'confirm':False},{'language':'en'},{'snapshot_sha256':'wrong'},{'extra':True}):
                with self.assertRaises(ValueError):ac.prepare(c,self.body(c,oid,**kw),self.T)
            body=self.body(c,oid)
            did=ac.prepare(c,body,self.T)
            ac.revoke(c,{'confirm':True,'draft':did},self.T+1)
            self.assertEqual(ac.status(c)['drafts'][0]['state'],'revoked')
            with self.assertRaises(ValueError):ac.preview(c,did)
            with self.assertRaises(ValueError):ac.prepare(c,body,self.T+2)
            with self.assertRaises(ValueError):ac.revoke(c,{'confirm':True,'draft':did},self.T+3)
            self.assertEqual(len(ac.status(c)['events']),2)

    def test_title_escaping_and_reference_changes(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            c.execute("UPDATE projects SET title=? WHERE id=?",('<script>alert(1)</script>',pid))
            body=self.body(c,oid)
            did=ac.prepare(c,body,self.T)
            self.assertIn('&lt;script&gt;',ac.preview(c,did)['html'])
            self.assertNotIn('<script>',ac.preview(c,did)['html'])
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
            self.assertEqual(ac.status(c)['drafts'][0]['state'],'reference_changed')
            with self.assertRaises(ValueError):ac.preview(c,did)
            with self.assertRaises(ValueError):ac.prepare(c,body,self.T+1)

    def test_review_gate(self):
        oid,aid,pid=self.fixture(review='revise')
        with s.db() as c:
            with self.assertRaises(ValueError):ac.prepare(c,self.body(c,oid),self.T)
            self.assertEqual(ac.status(c)['drafts'],[])

    def test_http_owner_only_no_provider(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:body=self.body(c,oid)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=AssertionError('No provider')) as req:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            port=server.server_address[1]
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def call(path,body=None,auth=True):
                h={'Content-Type':'application/json'}
                if auth:h['X-Session']=s.SESSION
                data=None if body is None else json.dumps(body).encode()
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/api/'+path,headers=h,data=data)) as r:return json.load(r)
            try:
                with patch.object(s,'PORT',port):
                    with self.assertRaises(urllib.error.HTTPError) as err:call('acquisition/prepare',body,False)
                    self.assertEqual(err.exception.code,403)
                    did=call('acquisition/prepare',body)['id']
                    with self.assertRaises(urllib.error.HTTPError):call('acquisition_preview?id='+str(did),auth=False)
                    self.assertEqual(call('acquisition_preview?id='+str(did))['classification'],'internal_draft')
                    audit=call('acquisition_audit')
                    self.assertEqual(audit['schema'],'aes-acquisition-audit-v1')
                    self.assertNotIn(s.SESSION,json.dumps(audit))
                    call('acquisition/revoke',{'confirm':True,'draft':did})
                    with self.assertRaises(urllib.error.HTTPError):call('acquisition_preview?id='+str(did))
                    req.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()
