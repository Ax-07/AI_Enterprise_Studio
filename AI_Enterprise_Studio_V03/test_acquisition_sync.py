import copy
import hashlib
import json
import os
import unittest
from unittest.mock import patch
import acquisition as ac
import acquisition_sync as sync
import business as b
import public_channel as ch
import serveur as s
import test_business as tb

class AcquisitionSyncTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T
    key=b'k'*32
    page='a'*32

    def setup_link(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            offer=b.status(c,self.T)['catalog'][0]
            did=ac.prepare(c,{'confirm':True,'offer':oid,'language':'fr','snapshot_sha256':offer['snapshot_sha256']},self.T)
            self.snapshot=offer['snapshot_sha256']
            grant={'confirm':True,'draft':did,'page':self.page,'snapshot_sha256':self.snapshot,'duration_seconds':600,'quota':3}
            sync.bind(c,grant,self.T)
        return did,aid,grant

    def envelope(self,t,items,total=None,**kw):
        p={'page':self.page,'snapshot':self.snapshot,'mode':'test','exported':t,
           'accepted_total':len(items) if total is None else total,'signals':items,'paid_orders':0,**kw}
        return {'payload':p,'signature':ch.sign(self.key,'export-v1',p)}

    def signal(self,i,kind='demo_request',segment=True):
        return {'id':format(i,'032x'),'participant':format(i,'064x'),'kind':kind,
                'segment':segment,'observed':self.T+1,'notice':ch.NOTICE_VERSION}

    def test_signed_reconciliation_and_withdrawal(self):
        did,aid,grant=self.setup_link()
        a=self.signal(1);z=self.signal(2,'purchase_question')
        first=self.envelope(self.T+2,[a,z])
        with s.db() as c:
            old=b.status(c,self.T)
            self.assertEqual(sync.ingest(c,self.key,self.page,first,self.T+2)['signals'],2)
            self.assertTrue(sync.ingest(c,self.key,self.page,first,self.T+2)['replayed'])
            st=sync.status(c,self.T+2)['links'][0]
            self.assertEqual(st['qualified_test'],1)
            self.assertEqual(st['intents']['purchase_question'],1)
            saved=c.execute('SELECT * FROM acquisition_test_signals').fetchone()
            self.assertNotEqual(saved['event_hash'],a['id'])
            self.assertNotEqual(saved['participant_hash'],a['participant'])
            second=self.envelope(self.T+3,[z],total=2)
            sync.ingest(c,self.key,self.page,second,self.T+3)
            self.assertEqual(sync.status(c,self.T+3)['links'][0]['qualified_test'],0)
            with self.assertRaises(ValueError):sync.ingest(c,self.key,self.page,first,self.T+3)
            self.assertEqual(sync.status(c,self.T+3)['links'][0]['test_signals'],1)
            self.assertEqual(b.status(c,self.T),old)
            self.assertEqual(s.used(c),10000)
            self.assertFalse(sync.status(c,self.T+125)['links'][0]['fresh'])

    def test_reject_invalid_batches_without_replacement(self):
        self.setup_link()
        a=self.signal(1)
        with s.db() as c:
            sync.ingest(c,self.key,self.page,self.envelope(self.T+2,[a]),self.T+2)
            invalid=[self.envelope(self.T+3,[a],mode='live'),
                     self.envelope(self.T+3,[a],snapshot='c'*64),
                     self.envelope(self.T+3,[a],paid_orders=1),
                     self.envelope(self.T+3,[a,a],total=2),
                     self.envelope(self.T+3,[{**a,'email':'private@example.invalid'}]),
                     self.envelope(self.T+3,[a],total=4),
                     self.envelope(self.T+3,[a],total=0),
                     self.envelope(self.T+3,[{**a,'observed':self.T+4}]),
                     self.envelope(self.T+2,[],total=1)]
            wrong=self.envelope(self.T+3,[],total=1);wrong['signature']='0'*64
            invalid.append(wrong)
            for batch in invalid:
                with self.assertRaises(ValueError):sync.ingest(c,self.key,self.page,batch,self.T+3)
                self.assertEqual(sync.status(c,self.T+3)['links'][0]['test_signals'],1)

    def test_revocation_reference_and_purge(self):
        did,aid,grant=self.setup_link()
        with s.db() as c:
            with self.assertRaises(ValueError):sync.bind(c,{**grant,'page':'b'*32},self.T)
            sync.ingest(c,self.key,self.page,self.envelope(self.T+2,[self.signal(1)]),self.T+2)
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
            self.assertEqual(sync.status(c,self.T+3)['links'][0]['state'],'reference_changed')
            with self.assertRaises(ValueError):sync.ingest(c,self.key,self.page,self.envelope(self.T+3,[],total=1),self.T+3)
            sync.purge(c,self.T+3)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM acquisition_test_signals').fetchone()[0],0)
            sync.revoke(c,{'confirm':True,'page':self.page},self.T+4)
            self.assertEqual(sync.status(c,self.T+4)['links'][0]['state'],'revoked')

    def test_polling_only_active_configured_test_link(self):
        self.setup_link()
        envelope=self.envelope(self.T+2,[self.signal(1)])
        with patch.dict(os.environ,{'AES_CHANNEL_TEST_KEY_HEX':''}),patch.object(sync,'fetch',side_effect=AssertionError('no transport')):
            self.assertEqual(sync.run_once(s,self.T+2),[])
        with patch.dict(os.environ,{'AES_CHANNEL_TEST_KEY_HEX':self.key.hex()}),patch.object(b,'now',return_value=self.T+2),patch.object(sync,'fetch',return_value=envelope) as fetch:
            self.assertTrue(sync.run_once(s,self.T+2)[0]['ok'])
            fetch.assert_called_once_with(self.page,self.key)
            self.assertEqual(sync.run_once(s,self.T+3),[])
            self.assertEqual(fetch.call_count,1)
        with s.db() as c:
            sync.revoke(c,{'confirm':True,'page':self.page},self.T+4)
        with patch.dict(os.environ,{'AES_CHANNEL_TEST_KEY_HEX':self.key.hex()}),patch.object(sync,'fetch',side_effect=AssertionError('no revoked transport')):
            self.assertEqual(sync.run_once(s,self.T+60),[])

    def test_real_channel_export_into_enterprise(self):
        self.setup_link()
        remote=ch.connect(':memory:');self.addCleanup(remote.close);ch.init(remote)
        m={'id':self.page,'mode':'test','snapshot':self.snapshot,'offer':5,'title':'Test',
           'description':'Fictif','limitations':'Pas de vente','price_cents':4900,'starts':self.T,'expires':self.T+600}
        ch.publish(remote,self.key,m,ch.sign(self.key,'publication-v1',m),self.T)
        g={'page':self.page,'snapshot':self.snapshot,'publication_hash':hashlib.sha256(ch.canonical(m).encode()).hexdigest(),
           'mode':'test','starts':self.T,'expires':self.T+300,'quota':3,'notice':ch.NOTICE_VERSION}
        ch.authorize_collection(remote,self.key,g,ch.sign(self.key,'collection-v1',g),self.T)
        remote.execute('BEGIN IMMEDIATE')
        event=ch.record(remote,self.key,self.page,ch.participant_token(self.key,self.page),
                        {'kind':'demo_request','segment':True,'consent':True,'notice':ch.NOTICE_VERSION},self.T+1)
        remote.commit()
        with s.db() as c:
            sync.ingest(c,self.key,self.page,ch.export(remote,self.key,self.page,self.T+2),self.T+2)
            self.assertEqual(sync.status(c,self.T+2)['links'][0]['qualified_test'],1)
            ch.withdraw(remote,event['id'],event['delete_token'])
            sync.ingest(c,self.key,self.page,ch.export(remote,self.key,self.page,self.T+3),self.T+3)
            self.assertEqual(sync.status(c,self.T+3)['links'][0]['test_signals'],0)
            self.assertEqual(sync.status(c,self.T+3)['real_prospects'],0)
