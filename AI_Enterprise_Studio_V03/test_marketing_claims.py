"""Independent claims checks using persisted synthetic benchmark captures."""
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
import marketing_templates as templates
import serveur as s
import test_marketing as tm
import verification as verifier
from departments import marketing_claims


class MarketingClaimsTests(unittest.TestCase):
    setUp=tm.MarketingTests.setUp
    start=tm.MarketingTests.start
    historical=tm.MarketingTests.historical
    prepare=tm.MarketingTests.prepare
    fixture=tm.MarketingTests.fixture
    T=tm.MarketingTests.T
    benchmark_fixture=tm.MarketingTests.benchmark_fixture

    def prepared(self,c,aid):
        rid,result=self.benchmark_fixture(c,aid)
        did=h.run_once(c,self.T)[0]
        bundle=mk.prepare(c,did,self.T)
        return did,rid,result,bundle['payload']

    def replace(self,c,rid,result):
        c.execute('UPDATE laboratory_runs SET result=? WHERE id=?',(json.dumps(result),rid))

    def blocked(self,c,did,payload):
        self.assertEqual(review.review(c,did,payload),
                         {'state':'blocked','publication_authorized':False,'limit':review.LIMIT})

    def test_exact_evidence_read_only_and_no_execution(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                with patch.object(s,'request',side_effect=AssertionError('no provider')) as req, patch.object(verifier,'browser_results',side_effect=AssertionError('no browser')) as browser:
                    facts=review.evidence(c,did)
                    self.assertEqual(facts,payload['facts'])
                    self.assertEqual(facts['laboratory_run'],rid)
                    self.assertEqual(facts['evidence_sha256'],b.digest(result))
                    self.assertEqual((facts['tp'],facts['fp'],facts['fn']),(42,0,0))
                    self.assertEqual(review.review(c,did,payload),
                                     {'state':'technical_pass','payload_sha256':b.digest(payload),
                                      'publication_authorized':False,'limit':review.LIMIT})
                    req.assert_not_called();browser.assert_not_called()
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')

    def test_all_channels_and_metadata_must_match_exactly(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            for path,value in ((('content','landing','price'),'Gratuit'),
                               (('content','youtube','description'),'Garantie 100 %'),
                               (('content','social','text'),'Achetez maintenant'),
                               (('content','media_policy','generated_video'),True),
                               (('facts','tp'),999),
                               (('revision',),templates.REVISION+1),
                               (('language',),'en')):
                with self.subTest(path=path):
                    altered=copy.deepcopy(payload);node=altered
                    for key in path[:-1]:node=node[key]
                    node[path[-1]]=value
                    self.blocked(c,did,altered)
            self.blocked(c,did,{**payload,'publication_authorized':True})

    def test_modified_metrics_cannot_be_used_even_with_matching_render(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            altered=copy.deepcopy(result);altered['metrics']['tp']=999
            self.replace(c,rid,altered)
            forged=copy.deepcopy(payload);forged['facts']['tp']=999
            facts=forged['facts']
            forged['content']=templates.render(facts['price_cents'],facts['size'],facts['tp'],facts['fp'],facts['fn'])
            self.blocked(c,did,forged)
            with self.assertRaisesRegex(ValueError,'Mesures historiques incohérentes'):
                review.evidence(c,did)

    def test_missing_or_incomplete_cases_fail_closed(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            for cases in (None,[],result['cases'][:-1]):
                self.replace(c,rid,{**result,'cases':cases})
                self.blocked(c,did,payload)
            altered=copy.deepcopy(result);altered['cases'][0]['status']='failed'
            self.replace(c,rid,altered)
            self.blocked(c,did,payload)

    def test_proof_hashes_and_current_artifact_required(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            for key in ('sha256','fixture_sha256'):
                self.replace(c,rid,{**result,key:'0'*64})
                self.blocked(c,did,payload)
            self.replace(c,rid,result)
            c.execute("UPDATE artifacts SET content=content||' ' WHERE id=?",(aid,))
            self.blocked(c,did,payload)

    def test_revoked_draft_cannot_be_approved(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            ac.revoke(c,{'confirm':True,'draft':did},self.T+1)
            self.blocked(c,did,payload)
            with self.assertRaises(ValueError):mk.packet(c,did)

    def test_legacy_callbacks_and_failure_contract(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result,payload=self.prepared(c,aid)
            with patch.object(review,'evidence',side_effect=RuntimeError('fixture')) as evidence:
                self.blocked(c,did,payload)
                evidence.assert_called_once_with(c,did)
            with patch.object(marketing_claims,'evidence',return_value={'fixture':True}) as evidence:
                self.assertEqual(review.evidence(c,did),{'fixture':True})
                evidence.assert_called_once_with(c,did,ac=review.ac,lab=review.lab,json=review.json,b=review.b)


if __name__=='__main__':
    unittest.main()
