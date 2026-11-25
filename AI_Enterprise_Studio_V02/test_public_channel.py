import hashlib
import json
import sqlite3
import unittest
import public_channel as ch

class PublicChannelTests(unittest.TestCase):
    def setUp(self):
        self.c=ch.connect(':memory:')
        ch.init(self.c)
        self.addCleanup(self.c.close)
        self.key=b'k'*32
        self.t=1800000000
        self.id='a'*32
        self.m={'id':self.id,'mode':'test','snapshot':'b'*64,'offer':5,
                'title':'Audit fictif','description':'Exemple de catalogue','limitations':'Pas de vente',
                'price_cents':4900,'starts':self.t,'expires':self.t+600}
        self.g={'page':self.id,'snapshot':self.m['snapshot'],
                'publication_hash':hashlib.sha256(ch.canonical(self.m).encode()).hexdigest(),
                'mode':'test','starts':self.t,'expires':self.t+300,'quota':2,'notice':ch.NOTICE_VERSION}
        self.b={'kind':'demo_request','segment':True,'consent':True,'notice':ch.NOTICE_VERSION}
    def signed(self,domain,payload):
        return ch.sign(self.key,domain,payload)
    def publish(self,**kw):
        m={**self.m,**kw}
        return ch.publish(self.c,self.key,m,self.signed('publication-v1',m),self.t)
    def grant(self,**kw):
        g={**self.g,**kw}
        return ch.authorize_collection(self.c,self.key,g,self.signed('collection-v1',g),self.t)
    def record(self,token=None,t=None,**kw):
        token=token or ch.participant_token(self.key,self.id)
        self.c.execute('BEGIN IMMEDIATE')
        try:
            result=ch.record(self.c,self.key,self.id,token,{**self.b,**kw},self.t if t is None else t)
            self.c.commit()
            return result
        except Exception:
            self.c.rollback()
            raise
    def revoke(self,scope):
        r={'page':self.id,'scope':scope}
        return ch.revoke(self.c,self.key,r,self.signed('revocation-v1',r),self.t+1)
    def test_separate_permissions_exact_signed_grants(self):
        with self.assertRaises(ValueError):self.grant()
        with self.assertRaises(ValueError):self.publish(mode='live')
        with self.assertRaises(ValueError):self.publish(expires=self.t+86401)
        with self.assertRaises(ValueError):ch.publish(self.c,self.key,self.m,'0'*64,self.t)
        self.publish()
        self.assertFalse(ch.page(self.c,self.id,self.t)['collection_open'])
        with self.assertRaises(ValueError):self.record()
        for kw in ({'mode':'live'},{'snapshot':'c'*64},{'publication_hash':'0'*64},
                   {'quota':1001},{'expires':self.t+601},{'notice':'wrong'}):
            with self.assertRaises(ValueError):self.grant(**kw)
        self.grant()
        self.assertTrue(ch.page(self.c,self.id,self.t)['collection_open'])
        self.assertEqual(self.grant(),self.id)
        with self.assertRaises(ValueError):self.grant(quota=3)
    def test_consent_quota_deduplication_and_no_sales(self):
        self.publish();self.grant()
        token=ch.participant_token(self.key,self.id)
        for kw in ({'consent':False},{'notice':'other'},{'segment':1},{'kind':'paid_order'},{'email':'private@example.invalid'}):
            with self.assertRaises(ValueError):self.record(token,**kw)
        with self.assertRaises(ValueError):self.record(token[:-1]+('1' if token[-1]!='1' else '2'))
        one=self.record(token)
        self.assertFalse(one['paid_order'])
        with self.assertRaises(ValueError):self.record(token,kind='interest')
        self.record(kind='purchase_question')
        self.assertFalse(ch.page(self.c,self.id,self.t)['collection_open'])
        with self.assertRaises(ValueError):self.record()
        batch=ch.export(self.c,self.key,self.id,self.t)
        ch.check(self.key,'export-v1',batch['payload'],batch['signature'])
        self.assertEqual(batch['payload']['accepted_total'],2)
        self.assertEqual(batch['payload']['paid_orders'],0)
        self.assertNotIn(token,json.dumps(batch))
        self.assertNotIn(one['delete_token'],json.dumps(batch))
    def test_withdraw_does_not_restore_quota_and_retention(self):
        self.publish();self.grant()
        token=ch.participant_token(self.key,self.id)
        one=self.record(token)
        self.assertFalse(ch.withdraw(self.c,one['id'],'0'*64))
        self.assertTrue(ch.withdraw(self.c,one['id'],one['delete_token']))
        self.assertFalse(ch.withdraw(self.c,one['id'],one['delete_token']))
        with self.assertRaises(ValueError):self.record(token)
        self.record()
        self.assertEqual(ch.export(self.c,self.key,self.id,self.t)['payload']['accepted_total'],2)
        self.assertEqual(len(ch.export(self.c,self.key,self.id,self.t)['payload']['signals']),1)
        self.assertEqual(ch.export(self.c,self.key,self.id,self.t+ch.RETENTION)['payload']['signals'],[])
    def test_expiry_revocation_and_no_reactivation(self):
        self.publish();self.grant()
        with self.assertRaises(ValueError):self.record(t=self.t+300)
        self.revoke('collection')
        self.assertFalse(ch.page(self.c,self.id,self.t+2)['collection_open'])
        with self.assertRaises(ValueError):self.grant()
        self.revoke('publication')
        with self.assertRaises(ValueError):ch.page(self.c,self.id,self.t+2)
        with self.assertRaises(ValueError):self.publish()
    def test_transaction_rolls_back_without_consuming_quota(self):
        self.publish();self.grant()
        self.c.execute('BEGIN IMMEDIATE')
        ch.record(self.c,self.key,self.id,ch.participant_token(self.key,self.id),self.b,self.t)
        self.c.rollback()
        self.assertEqual(ch.export(self.c,self.key,self.id,self.t)['payload']['accepted_total'],0)
        self.assertEqual(ch.export(self.c,self.key,self.id,self.t)['payload']['signals'],[])
