import json,unittest,threading,urllib.request,urllib.error
from unittest.mock import patch
import serveur as s,moteur as m,autopilot as a,portfolio as p,commercial as co,business as b
import test_commercial
from test_commercial import PLAN,ECO

class BusinessTests(unittest.TestCase):
    setUp=test_commercial.CommercialTests.setUp
    start=test_commercial.CommercialTests.start
    historical=test_commercial.CommercialTests.historical
    prepare=test_commercial.CommercialTests.prepare
    T=1800000000
    def fixture(self,metric='paid_order_future',review='study_further',economics=ECO):
        *_,fixed,opp,old,new=self.historical()
        cid=self.prepare(old,search_cap=0)
        with s.db() as c:
            mid=m.create(s,c,'Préparation','cloud',fixed)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,fixed))
            p.attach(c,mid,old,'test')
            oid=co.execute(c,{'mission':mid,'agent':'HERMES'},'commercial_offer','',json.dumps({**PLAN,'metric':metric}),'')['offer']
            co.execute(c,{'mission':mid,'agent':'MIDAS'},'commercial_economics',str(oid),json.dumps(economics),'')
            co.execute(c,{'mission':mid,'agent':'SENTINEL'},'commercial_review',str(oid),json.dumps({'verdict':review,'gaps':'Données documentaires manquantes; étude seulement.'}),'')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
            return oid,fixed,old
    def grant_body(self,oid,**kw):
        with s.db() as c:
            offer=next(x for x in b.status(c,self.T)['catalog'] if x['offer']==oid)
        return {'confirm':True,'offer':oid,'metric':'qualified_interest','sample_size':2,'success_min':1,'duration_days':1,'snapshot_sha256':offer['snapshot_sha256'],**kw}
    def authorize(self,oid,**kw):
        body=self.grant_body(oid,**kw)
        with s.db() as c:return b.authorize(c,body,self.T)
    def observation(self,tid,i=1,**kw):
        return {'confirm':True,'trial':tid,'participant_ref':'opaque-participant-'+str(i),'evidence_ref':'opaque-evidence-'+str(i),'outcome':'interest','observed_at':self.T+1,'consent_attested':True,**kw}
    def receipt_body(self,oid,i=1,**kw):
        return {'confirm':True,'offer':oid,'reference':'opaque-transaction-'+str(i),'mode':'test','kind':'payment','parent':None,'amount_cents':4900,'occurred_at':self.T,'source_attested':True,**kw}
    def test_migration_catalog_no_automatic_authority(self):
        oid,aid,pid=self.fixture()
        with patch.object(s,'request',side_effect=AssertionError('No provider')) as req:
            s.init();s.init();req.assert_not_called()
        with s.db() as c:
            d=b.status(c,self.T)
            self.assertEqual(len(d['catalog']),1)
            o=d['catalog'][0]
            self.assertEqual(o['offer'],oid);self.assertEqual(o['artifact'],aid)
            self.assertEqual(o['state'],'preparation_incomplete');self.assertTrue(o['observation_eligible'])
            self.assertFalse(o['sale_authorized']);self.assertFalse(d['external_authorized'])
            self.assertEqual(d['trials'],[]);self.assertEqual(d['receipts'],[])
            self.assertFalse(d['verified_live_available']);self.assertEqual(d['verified_live_cents'],0)
            self.assertEqual(s.used(c),10000)
            self.assertFalse(co.project_status(c,pid)['offer']['external_authorized'])
    def test_grant_scope_and_distinct_consent_sample_cap(self):
        oid,aid,pid=self.fixture()
        for kw in ({'confirm':False},{'metric':'paid_order_future'},{'duration_days':15},{'sample_size':21},{'snapshot_sha256':'bad'},{'success_min':3},{'extra':True}):
            with self.assertRaises(ValueError):self.authorize(oid,**kw)
        tid=self.authorize(oid)
        with self.assertRaises(ValueError):self.authorize(oid)
        with s.db() as c:
            for kw in ({'consent_attested':False},{'observed_at':self.T-1},{'outcome':'paid_order'},{'participant_ref':'person@example.com'}):
                with self.assertRaises(ValueError):b.observe(c,self.observation(tid,**kw),self.T+2)
            b.observe(c,self.observation(tid),self.T+2)
            for kw in ({'participant_ref':'opaque-participant-1'},{'evidence_ref':'opaque-evidence-1'}):
                with self.assertRaises(ValueError):b.observe(c,self.observation(tid,2,**kw),self.T+2)
            st=b.status(c,self.T+2)['trials'][0]
            self.assertTrue(st['threshold_reached']);self.assertFalse(st['sample_complete'])
            b.observe(c,self.observation(tid,2,outcome='no_interest'),self.T+2)
            with self.assertRaises(ValueError):b.observe(c,self.observation(tid,3),self.T+2)
            st=b.status(c,self.T+2)['trials'][0]
            self.assertEqual(st['effective_state'],'sample_complete');self.assertEqual(st['positive'],1)
            self.assertEqual(st['snapshot']['plan']['metric'],'paid_order_future')
            self.assertEqual(st['metric'],'qualified_interest')
            self.assertNotIn('opaque-participant-1',json.dumps(st));self.assertNotIn('opaque-evidence-1',json.dumps(st))
            b.close(c,{'confirm':True,'trial':tid},self.T+2)
            self.assertEqual(b.trial_row(c,tid)['close_reason'],'sample_complete')
    def test_expiry_revocation_and_modified_reference(self):
        oid,aid,pid=self.fixture()
        tid=self.authorize(oid)
        with s.db() as c:
            self.assertEqual(b.status(c,self.T+86400)['trials'][0]['effective_state'],'expired')
            with self.assertRaises(ValueError):b.observe(c,self.observation(tid),self.T+86400)
            self.assertEqual(b.status(c,self.T-1)['trials'][0]['effective_state'],'clock_error')
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
            self.assertEqual(b.status(c,self.T+2)['trials'][0]['effective_state'],'reference_changed')
            with self.assertRaises(ValueError):b.observe(c,self.observation(tid),self.T+2)
            b.close(c,{'confirm':True,'trial':tid},self.T+2)
            self.assertEqual(b.trial_row(c,tid)['state'],'closed')
    def test_revise_or_negative_economics_blocks_observation(self):
        oid,aid,pid=self.fixture(review='revise')
        with self.assertRaises(ValueError):self.authorize(oid)
        with s.db() as c:
            c.execute("UPDATE commercial_reviews SET review=? WHERE offer=?",(json.dumps({'verdict':'study_further','gaps':'Étude nécessaire'}),oid))
            eco={**ECO,'variable_cost_cents':10001}
            c.execute('UPDATE commercial_economics SET assumptions=?,result=? WHERE offer=?',(json.dumps(eco),json.dumps(co.economics_result(PLAN,eco)),oid))
        with self.assertRaises(ValueError):self.authorize(oid)
    def test_receipts_test_declared_refunds_never_verified(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            test=b.receipt(c,self.receipt_body(oid),self.T)
            live=b.receipt(c,self.receipt_body(oid,2,mode='owner_declared_live'),self.T)
            for kw in ({'mode':'verified_live'},{'source_attested':False},{'reference':'opaque-transaction-1','mode':'owner_declared_live'},
                       {'kind':'refund','parent':test,'amount_cents':5000},{'kind':'refund','parent':live},{'amount_cents':-1}):
                with self.assertRaises(ValueError):b.receipt(c,self.receipt_body(oid,3,**kw),self.T)
            b.receipt(c,self.receipt_body(oid,4,kind='refund',parent=test,amount_cents=900),self.T)
            with self.assertRaises(ValueError):b.receipt(c,self.receipt_body(oid,5,kind='refund',parent=test,amount_cents=4001),self.T)
            st=b.status(c,self.T)
            self.assertEqual(st['totals']['test'],{'gross_cents':4900,'refunds_cents':900,'net_cents':4000})
            self.assertEqual(st['totals']['owner_declared_live']['net_cents'],4900)
            self.assertEqual(st['verified_live_cents'],0);self.assertFalse(st['external_authorized'])
            self.assertEqual(st['external_spend_cents'],0)
            self.assertNotIn('opaque-transaction-1',json.dumps(st))
    def test_http_owner_session_no_worker_or_provider(self):
        oid,aid,pid=self.fixture()
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=AssertionError('No provider')) as req,patch.object(a,'worker',side_effect=AssertionError('No worker')) as worker,patch.object(b,'now',return_value=self.T):
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];url=f'http://127.0.0.1:{port}'
            def post(path,body,auth=True):
                h={'Content-Type':'application/json'}
                if auth:h['X-Session']=s.SESSION
                with urllib.request.urlopen(urllib.request.Request(url+'/api/business/'+path,data=json.dumps(body).encode(),headers=h)) as r:return json.load(r)
            try:
                with patch.object(s,'PORT',port):
                    with self.assertRaises(urllib.error.HTTPError) as err:post('authorize',self.grant_body(oid),False)
                    self.assertEqual(err.exception.code,403)
                    tid=post('authorize',self.grant_body(oid))['id']
                    post('observe',self.observation(tid,observed_at=self.T))
                    post('close',{'confirm':True,'trial':tid})
                    with urllib.request.urlopen(urllib.request.Request(url+'/api/business_audit',headers={'X-Session':s.SESSION})) as r:
                        d=json.load(r);self.assertEqual(d['business']['trials'][0]['effective_state'],'closed')
                        self.assertNotIn(s.SESSION,json.dumps(d))
                    with s.db() as c:self.assertEqual(s.used(c),10000)
                    req.assert_not_called();worker.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()
