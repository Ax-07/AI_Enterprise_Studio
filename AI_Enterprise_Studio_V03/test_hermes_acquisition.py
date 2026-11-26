import json
import unittest
from unittest.mock import patch

import acquisition as ac
import business as b
import hermes_acquisition as h
import laboratory as lab
import serveur as s
import test_business as tb

class HermesAcquisitionTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def test_deterministic_automatic_preparation_no_external_side_effect(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            before=b.status(c,self.T)
            cost=s.used(c)
            made=h.run_once(c,self.T)
            self.assertEqual(len(made),1)
            did=made[0]
            p=h.packet(c,did)
            self.assertEqual(p['offer'],oid)
            self.assertEqual(p['price_cents'],before['catalog'][0]['plan']['price_cents'])
            self.assertEqual(p['snapshot_sha256'],before['catalog'][0]['snapshot_sha256'])
            self.assertEqual(p['product_demo']['status'],'unavailable')
            self.assertFalse(p['product_demo']['new_execution'])
            self.assertEqual(h.run_once(c,self.T+1),[])
            self.assertEqual(s.used(c),cost)
            self.assertEqual(b.status(c,self.T),before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM acquisition_test_channels').fetchone()[0],0)
            self.assertFalse(h.status(c)['external_authorized'])

    def test_revoked_and_stale_packet_not_reused(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did=h.run_once(c,self.T)[0]
            ac.revoke(c,{'confirm':True,'draft':did},self.T+1)
            with self.assertRaises(ValueError):h.packet(c,did)
            self.assertEqual(h.run_once(c,self.T+2),[])
            self.assertEqual(h.status(c)['packets'][0]['state'],'unavailable')

    def test_agent_context_project_scope_and_market_permission(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            h.run_once(c,self.T)
            scope={'project':pid,'state':'actif','mission_state':'en cours','mode':'cloud',
                   'project_state':'active','permissions':json.dumps({'market':True})}
            with patch.object(h.commercial,'scope',return_value=scope):
                self.assertEqual(len(h.agent_context(c,1,'HERMES')['packets']),1)
                self.assertIsNone(h.agent_context(c,1,'ATLAS'))
                self.assertIsNone(h.agent_context(c,1,'NEXUS'))
                scope['project']=pid+1000
                self.assertEqual(h.agent_context(c,1,'HERMES')['packets'],[])
                scope['permissions']='{"market":false}'
                self.assertIsNone(h.agent_context(c,1,'HERMES'))
            with patch.object(h.commercial,'scope',return_value=None):
                self.assertIsNone(h.agent_context(c,1,'HERMES'))

    def test_demo_uses_matching_historical_evidence_not_expected_output(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
            c.execute("UPDATE artifacts SET name='audit_catalogue.html' WHERE id=?",(aid,))
            sha=lab.digest(row['content'])
            fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
            # Fixture for testing the retrieval contract only, not a product test.
            observed='historical captured output fixture'
            result={'sha256':sha,'fixture_sha256':lab.digest(lab.encode(fixtures)),
                    'cases':[{'name':'anomalies','status':'passed','output':observed}],
                    'metrics':{'tp':42,'fp':0,'fn':0}}
            rid=c.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,?,?,?,?,?,?,?)",
                          (aid,lab.PROFILE,lab.VERSION,300,lab.DEFAULT_SEED,sha,'passed',json.dumps(result))).lastrowid
            p={'offer_id':oid,'artifact_sha256':sha}
            demo=h._demo(c,p)
            self.assertEqual(demo['status'],'historical_evidence')
            self.assertEqual(demo['laboratory_run'],rid)
            self.assertEqual(demo['observed_output'],observed)
            self.assertEqual(len(json.loads(demo['input_json'])['rows']),300)
            self.assertFalse(demo['new_execution'])
            self.assertEqual(h._demo(c,{**p,'artifact_sha256':'0'*64})['status'],'unavailable')
            result['fixture_sha256']='0'*64
            c.execute('UPDATE laboratory_runs SET result=? WHERE id=?',(json.dumps(result),rid))
            self.assertEqual(h._demo(c,p)['status'],'unavailable')
