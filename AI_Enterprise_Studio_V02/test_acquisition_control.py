import http.client as http_client_module
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from wsgiref.simple_server import make_server

import acquisition as ac
import acquisition_control as ctl
import acquisition_sync as sync
import business as b
import public_channel as ch
import public_channel_http as http
import serveur as s
import test_business as tb

class AcquisitionControlTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T
    K=b'x'*32

    def setup_control(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            offer=b.status(c,self.T)['catalog'][0]
            snap=offer['snapshot_sha256']
            did=ac.prepare(c,{'confirm':True,'offer':oid,'language':'fr','snapshot_sha256':snap},self.T)
        self.stamp=self.T
        self.clock=lambda:self.stamp
        self.remote=ch.connect(':memory:')
        self.addCleanup(self.remote.close);ch.init(self.remote)
        env=patch.dict(os.environ,{'AES_CHANNEL_TEST_KEY_HEX':self.K.hex()});env.start();self.addCleanup(env.stop)
        return {'confirm':True,'draft':did,'snapshot_sha256':snap,'duration_seconds':600},aid

    def transport(self,op,body,key):
        if op=='status':return ch.inspect(self.remote,key,body['page'],body['nonce'],self.stamp)
        if op=='export':return ch.export(self.remote,key,body['page'],self.stamp)
        fn={'publish':ch.publish,'collect':ch.authorize_collection,'revoke':ch.revoke}[op]
        return {'id':fn(self.remote,key,body['payload'],body['signature'],self.stamp)}

    def activate(self,body,collection=False,transport=None):
        return ctl.activate(s,body,collection,request=transport or self.transport,clock=self.clock)

    def test_distinct_grants_and_confirmed_stop(self):
        body,aid=self.setup_control()
        pub=self.activate(body);page=pub['page']
        self.assertEqual(pub['state'],'published')
        self.assertFalse(ch.page(self.remote,page,self.stamp)['collection_open'])
        with s.db() as c:
            self.assertEqual(sync.status(c,self.stamp)['links'],[])
            with self.assertRaises(ValueError):ctl.prepare(c,body,self.stamp)
        self.stamp+=1
        collect={'confirm':True,'page':page,'quota':2,'duration_seconds':120}
        self.assertEqual(self.activate(collect,True)['state'],'collecting')
        self.assertTrue(ch.page(self.remote,page,self.stamp)['collection_open'])
        self.remote.execute('BEGIN IMMEDIATE')
        ch.record(self.remote,self.K,page,ch.participant_token(self.K,page),
            {'kind':'demo_request','segment':True,'consent':True,'notice':ch.NOTICE_VERSION},self.stamp)
        self.remote.commit()
        with s.db() as c:
            sync.ingest(c,self.K,page,ch.export(self.remote,self.K,page,self.stamp),self.stamp)
            self.assertEqual(sync.status(c,self.stamp)['links'][0]['qualified_test'],1)
        self.assertEqual(ctl.stop_remote(s,page,self.transport,self.clock)['state'],'revoked')
        with self.assertRaises(ValueError):ch.page(self.remote,page,self.stamp)
        with s.db() as c:
            self.assertEqual(sync.status(c,self.stamp)['links'][0]['state'],'revoked')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM acquisition_test_signals').fetchone()[0],0)
            self.assertEqual(b.status(c,self.stamp)['trials'],[])
            self.assertEqual(s.used(c),10000)

    def test_uncertain_activation_never_replayed_and_revocation_retried(self):
        body,aid=self.setup_control()
        calls=[]
        def interrupted(op,p,key):
            calls.append(op)
            if op=='publish':
                self.transport(op,p,key)
                raise ValueError('response lost')
            raise ValueError('offline')
        result=self.activate(body,transport=interrupted)
        self.assertEqual(result['state'],'revocation_pending')
        self.assertEqual(calls,['publish','revoke'])
        page=result['page']
        self.assertTrue(ch.page(self.remote,page,self.stamp))
        self.stamp+=30
        self.assertEqual(ctl.maintain(s,self.clock,self.transport)[0]['state'],'revoked')
        with self.assertRaises(ValueError):ch.page(self.remote,page,self.stamp)

    def test_revocation_before_delayed_publication(self):
        body,aid=self.setup_control()
        with s.db() as c:page,m=ctl.prepare(c,body,self.stamp)
        self.assertEqual(ctl.stop_remote(s,page,self.transport,self.clock)['state'],'revoked')
        with self.assertRaises(ValueError):ch.publish(self.remote,self.K,m,ch.sign(self.K,'publication-v1',m),self.stamp)
        p=ch.inspect(self.remote,self.K,page,'b'*32,self.stamp)['payload']
        self.assertFalse(p['exists']);self.assertTrue(p['publication_revoked'])

    def test_reference_change_stops_channel_and_nonce_replay_fails(self):
        body,aid=self.setup_control()
        result=self.activate(body);page=result['page']
        old=ch.inspect(self.remote,self.K,page,'b'*32,self.stamp)
        with self.assertRaises(ValueError):ctl.proof(page,self.K,lambda *a:old,self.stamp)
        with s.db() as c:c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
        self.stamp+=30
        self.assertEqual(ctl.maintain(s,self.clock,self.transport)[0]['state'],'revoked')

    def test_real_loopback_admin_transport(self):
        body,aid=self.setup_control()
        with tempfile.TemporaryDirectory() as tmp:
            app=http.application(str(Path(tmp)/'channel.sqlite3'),self.K,self.clock)
            srv=make_server('127.0.0.1',0,app,handler_class=http.QuietHandler)
            thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
            original=http_client_module.HTTPConnection
            try:
                with patch.object(sync.http.client,'HTTPConnection',side_effect=lambda host,port,timeout:original(host,srv.server_port,timeout=timeout)):
                    pub=ctl.activate(s,body,clock=self.clock)
                    self.assertEqual(pub['state'],'published')
                    self.assertEqual(ctl.activate(s,{'confirm':True,'page':pub['page'],'quota':2,'duration_seconds':60},True,clock=self.clock)['state'],'collecting')
                    self.assertEqual(ctl.stop_remote(s,pub['page'],clock=self.clock)['state'],'revoked')
            finally:srv.shutdown();srv.server_close();thread.join()

