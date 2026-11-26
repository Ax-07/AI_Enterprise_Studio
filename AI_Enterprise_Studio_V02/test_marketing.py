import copy
import json
import unittest
from unittest.mock import patch
import acquisition as ac
import business as b
import hermes_acquisition as h
import laboratory as lab
import marketing as mk
import marketing_review as review
import serveur as s
import test_business as tb

class MarketingTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def benchmark_fixture(self,c,aid):
        # Simulated stored browser capture for testing the retrieval contract, not a real product run.
        c.execute("UPDATE artifacts SET name='audit_catalogue.html' WHERE id=?",(aid,))
        sha=lab.digest(c.execute('SELECT content FROM artifacts WHERE id=?',(aid,)).fetchone()[0])
        fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
        observed=[{'name':f['name'],'passed':True,'elapsed_ms':1,
                   'output':f['expected_error'] if 'expected_error' in f else '\n'.join(f['expected']+[f['total']])} for f in fixtures]
        result={**lab.score(fixtures,observed),'sha256':sha,'fixture_sha256':lab.digest(lab.encode(fixtures))}
        rid=c.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,?,?,?,?,?,?,?)",
                      (aid,lab.PROFILE,lab.VERSION,300,lab.DEFAULT_SEED,sha,'passed',json.dumps(result))).lastrowid
        return rid,result

    def test_marketing_generation_and_exact_claims(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            rid,result=self.benchmark_fixture(c,aid)
            did=h.run_once(c,self.T)[0]
            old=b.status(c,self.T)
            self.assertEqual(mk.run_once(c,self.T),[did])
            self.assertEqual(mk.run_once(c,self.T+1),[])
            bundle=mk.packet(c,did);p=bundle['payload']
            self.assertEqual(bundle['review']['state'],'technical_pass')
            self.assertFalse(bundle['review']['publication_authorized'])
            self.assertEqual(p['facts']['tp'],42)
            self.assertEqual(p['facts']['laboratory_run'],rid)
            self.assertIn('300 lignes synthétiques',p['content']['landing']['evidence'])
            self.assertFalse(p['content']['media_policy']['generated_video'])
            self.assertEqual(b.status(c,self.T),old)
            self.assertEqual(s.used(c),10000)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM acquisition_test_channels').fetchone()[0],0)
            altered=copy.deepcopy(p);altered['content']['landing']['evidence']='Performance garantie à 100 %'
            self.assertEqual(review.review(c,did,altered)['state'],'blocked')
            result['metrics']['tp']=999
            c.execute('UPDATE laboratory_runs SET result=? WHERE id=?',(json.dumps(result),rid))
            self.assertEqual(review.review(c,did,p)['state'],'blocked')
            with self.assertRaises(ValueError):mk.packet(c,did)

    def test_unsupported_product_stays_unavailable(self):
        self.fixture()
        with s.db() as c:
            did=h.run_once(c,self.T)[0]
            self.assertEqual(mk.run_once(c,self.T),[])
            self.assertEqual(mk.status(c)['drafts'][0]['state'],'unavailable')
            with self.assertRaises(ValueError):mk.packet(c,did)

    def test_revocation_and_scoped_context(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            self.benchmark_fixture(c,aid)
            did=h.run_once(c,self.T)[0];mk.run_once(c,self.T)
            scope={'project':pid,'state':'actif','mission_state':'en cours','mode':'cloud',
                   'project_state':'active','permissions':json.dumps({'market':True,'tests':True})}
            with patch.object(mk.commercial,'scope',return_value=scope):
                self.assertEqual(len(mk.agent_context(c,1,'SENTINEL')['drafts']),1)
                self.assertIsNone(mk.agent_context(c,1,'ATLAS'))
                scope['permissions']='{"market":true,"tests":false}'
                self.assertIsNone(mk.agent_context(c,1,'SENTINEL'))
                scope['project']=pid+1000
                self.assertEqual(mk.agent_context(c,1,'HERMES')['drafts'],[])
            ac.revoke(c,{'confirm':True,'draft':did},self.T+1)
            with self.assertRaises(ValueError):mk.packet(c,did)
            self.assertEqual(mk.status(c)['drafts'][0]['state'],'unavailable')
