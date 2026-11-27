"""Historical demonstration retrieval contracts; no execution or paid calls."""
import json
import unittest
from unittest.mock import patch

import hermes_acquisition as h
import laboratory as lab
import serveur as s
import verification as verifier
import test_business as tb
from departments import product_demonstrations as demos


class DemonstrationDepartmentTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def evidence(self,c,oid,aid):
        c.execute("UPDATE artifacts SET name='audit_catalogue.html' WHERE id=?",(aid,))
        sha=lab.digest(c.execute('SELECT content FROM artifacts WHERE id=?',(aid,)).fetchone()[0])
        fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
        observed='Capture historique synthétique distincte des réponses attendues'
        result={'sha256':sha,'fixture_sha256':lab.digest(lab.encode(fixtures)),
                'cases':[{'name':'anomalies','status':'passed','output':observed}],
                'metrics':{'tp':42,'fp':0,'fn':0}}
        rid=c.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,?,?,?,?,?,?,?)",
                      (aid,lab.PROFILE,lab.VERSION,300,lab.DEFAULT_SEED,sha,'passed',json.dumps(result))).lastrowid
        return {'offer_id':oid,'artifact_sha256':sha},rid,result

    def replace(self,c,rid,result):
        c.execute('UPDATE laboratory_runs SET result=? WHERE id=?',(json.dumps(result),rid))

    def test_exact_historical_capture_and_read_only(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                with patch.object(verifier,'browser_results',side_effect=AssertionError('no browser')) as browser:
                    with patch.object(s,'request',side_effect=AssertionError('no provider')) as request:
                        demo=h._demo(c,payload)
                        self.assertEqual(demo['status'],'historical_evidence')
                        self.assertEqual(demo['laboratory_run'],rid)
                        self.assertEqual(demo['observed_output'],result['cases'][0]['output'])
                        self.assertEqual(demo['metrics'],result['metrics'])
                        self.assertEqual(len(json.loads(demo['input_json'])['rows']),300)
                        self.assertFalse(demo['new_execution'])
                        self.assertEqual(demo['limit'],lab.LIMIT)
                        self.assertEqual(h._demo(c,payload),demo)
                        browser.assert_not_called();request.assert_not_called()
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')

    def test_absent_or_unsupported_product_never_invents_capture(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            sha=lab.digest(c.execute('SELECT content FROM artifacts WHERE id=?',(aid,)).fetchone()[0])
            for offer in (oid,oid+9999):
                demo=h._demo(c,{'offer_id':offer,'artifact_sha256':sha})
                self.assertEqual(demo['status'],'unavailable')
                self.assertNotIn('observed_output',demo)
                self.assertFalse(demo['new_execution'])

    def test_exact_artifact_and_fixture_hashes_required(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            self.assertEqual(h._demo(c,{**payload,'artifact_sha256':'0'*64})['status'],'unavailable')
            for key in ('fixture_sha256','sha256'):
                self.replace(c,rid,{**result,key:'0'*64})
                self.assertEqual(h._demo(c,payload)['status'],'unavailable')
            self.replace(c,rid,result)
            c.execute("UPDATE artifacts SET content=content||' ' WHERE id=?",(aid,))
            self.assertEqual(h._demo(c,payload)['status'],'unavailable')

    def test_latest_canonical_failure_does_not_fall_back(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            self.assertEqual(h._demo(c,payload)['status'],'historical_evidence')
            c.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,?,?,?,?,?,?,?)",
                      (aid,lab.PROFILE,lab.VERSION,300,lab.DEFAULT_SEED,payload['artifact_sha256'],'failed',json.dumps(result)))
            self.assertEqual(h._demo(c,payload)['status'],'unavailable')

    def test_missing_failed_or_nontext_capture_refused(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            for cases in ([],[{'name':'anomalies','status':'failed','output':'x'}],
                          [{'name':'anomalies','status':'passed','output':123}],
                          [{'name':'sain','status':'passed','output':'x'}]):
                with self.subTest(cases=cases):
                    self.replace(c,rid,{**result,'cases':cases})
                    self.assertEqual(h._demo(c,payload)['status'],'unavailable')

    def test_nonterminated_or_nonproduction_source_refused(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            mid=c.execute('SELECT mission FROM artifacts WHERE id=?',(aid,)).fetchone()[0]
            c.execute("UPDATE missions SET state='bloquée' WHERE id=?",(mid,))
            self.assertEqual(h._demo(c,payload)['status'],'unavailable')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            c.execute("UPDATE artifacts SET agent='ORION' WHERE id=?",(aid,))
            self.assertEqual(h._demo(c,payload)['status'],'unavailable')

    def test_legacy_dependencies_resolved_at_call_time(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            payload,rid,result=self.evidence(c,oid,aid)
            with patch.object(lab,'canonical',return_value=None) as canonical:
                self.assertEqual(h._demo(c,payload)['status'],'unavailable')
                canonical.assert_called_once()
            with patch.object(demos,'demo',return_value={'fixture':True}) as demo:
                self.assertEqual(h._demo(c,payload),{'fixture':True})
                demo.assert_called_once_with(c,payload,lab=h.lab,json=h.json)


if __name__=='__main__':
    unittest.main()
