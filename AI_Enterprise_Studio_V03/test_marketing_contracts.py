"""End-to-end local marketing contracts, without provider or public-channel calls."""
import json
import unittest
from unittest.mock import patch

import acquisition as ac
import business as b
import hermes_acquisition as h
import laboratory as lab
import marketing as mk
import marketing_review as review
import moteur as m
import serveur as s
import test_marketing as tm
import verification as verifier


class MarketingFlowTests(unittest.TestCase):
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
        self.assertEqual(mk.run_once(c,self.T),[did])
        return did,rid,result

    def counts(self,c):
        return tuple(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                     for table in ('acquisition_drafts','acquisition_events','hermes_preparations',
                                   'marketing_drafts','laboratory_runs','acquisition_test_channels',
                                   'acquisition_test_links','acquisition_test_signals'))

    def test_full_chain_persisted_exact_evidence_and_no_commercial_effect(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            baseline=b.status(c,self.T);cost=s.used(c)
            with patch.object(s,'request',side_effect=AssertionError('no provider')) as req, patch.object(verifier,'browser_results',side_effect=AssertionError('no browser')) as browser:
                did,rid,result=self.prepared(c,aid)
                preview=ac.preview(c,did);packet=h.packet(c,did);bundle=mk.packet(c,did)
                facts=bundle['payload']['facts'];demo=packet['product_demo']
                self.assertEqual(preview['snapshot_sha256'],packet['snapshot_sha256'])
                self.assertEqual(packet['snapshot_sha256'],facts['snapshot_sha256'])
                self.assertEqual(preview['artifact_sha256'],facts['artifact_sha256'])
                self.assertEqual(packet['price_cents'],facts['price_cents'])
                self.assertEqual(demo['laboratory_run'],rid)
                self.assertEqual(facts['laboratory_run'],rid)
                self.assertEqual(facts['evidence_sha256'],b.digest(result))
                self.assertEqual(demo['metrics']['tp'],facts['tp'])
                self.assertFalse(demo['new_execution'])
                self.assertEqual(bundle['review']['state'],'technical_pass')
                self.assertFalse(bundle['review']['publication_authorized'])
                self.assertFalse(bundle['payload']['content']['media_policy']['generated_video'])
                self.assertEqual(preview['demo']['real_observations'],0)
                self.assertEqual(preview['demo']['paid_orders'],0)
                self.assertEqual(self.counts(c),(1,1,1,1,1,0,0,0))
                self.assertEqual(b.status(c,self.T),baseline)
                self.assertEqual(s.used(c),cost)
                req.assert_not_called();browser.assert_not_called()
        s.init()
        with s.db() as c:
            self.assertEqual(h.run_once(c,self.T+1),[])
            self.assertEqual(mk.run_once(c,self.T+1),[])
            self.assertEqual(mk.packet(c,did),bundle)
            self.assertEqual(self.counts(c),(1,1,1,1,1,0,0,0))

    def test_changed_historical_capture_invalidates_both_packets_without_rewriting(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result=self.prepared(c,aid)
            saved=mk.packet(c,did)['payload']
            old=tuple(c.execute('SELECT payload,payload_sha256 FROM marketing_drafts WHERE draft=?',(did,)).fetchone())
            result['metrics']['tp']=999
            c.execute('UPDATE laboratory_runs SET result=? WHERE id=?',(json.dumps(result),rid))
            self.assertEqual(ac.status(c)['drafts'][0]['state'],'draft')
            self.assertEqual(h.status(c)['packets'][0]['state'],'unavailable')
            self.assertEqual(mk.status(c)['drafts'][0]['state'],'unavailable')
            self.assertEqual(review.review(c,did,saved)['state'],'blocked')
            self.assertEqual(h.run_once(c,self.T+1),[])
            self.assertEqual(mk.run_once(c,self.T+1),[])
            self.assertEqual(tuple(c.execute('SELECT payload,payload_sha256 FROM marketing_drafts WHERE draft=?',(did,)).fetchone()),old)
            self.assertEqual(self.counts(c),(1,1,1,1,1,0,0,0))

    def test_actual_campaign_scope_agent_permissions_and_revocation(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did,rid,result=self.prepared(c,aid)
        cid=self.prepare(pid,search_cap=0)
        with s.db() as c:
            mid=m.create(s,c,'Contexte marketing','cloud',aid)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'commercial',?)",(cid,mid,aid))
            self.assertEqual([x['draft'] for x in h.agent_context(c,mid,'HERMES')['packets']],[did])
            self.assertEqual([x['draft'] for x in mk.agent_context(c,mid,'SENTINEL')['drafts']],[did])
            self.assertIsNone(h.agent_context(c,mid,'SENTINEL'))
            self.assertIsNone(mk.agent_context(c,mid,'NEXUS'))
            c.execute("UPDATE campaigns SET permissions=? WHERE id=?",(json.dumps({'market':True,'tests':False,'research':True,'production':False}),cid))
            self.assertIsNone(mk.agent_context(c,mid,'SENTINEL'))
            self.assertEqual(len(mk.agent_context(c,mid,'HERMES')['drafts']),1)
            other=c.execute('SELECT id FROM projects WHERE id!=? ORDER BY id LIMIT 1',(pid,)).fetchone()[0]
            c.execute('UPDATE campaign_projects SET project=? WHERE campaign=?',(other,cid))
            self.assertEqual(h.agent_context(c,mid,'HERMES')['packets'],[])
            self.assertEqual(mk.agent_context(c,mid,'HERMES')['drafts'],[])
            c.execute('UPDATE campaign_projects SET project=? WHERE campaign=?',(pid,cid))
            ac.revoke(c,{'confirm':True,'draft':did},self.T+1)
            self.assertEqual(h.agent_context(c,mid,'HERMES')['packets'],[])
            self.assertEqual(mk.agent_context(c,mid,'HERMES')['drafts'][0]['state'],'unavailable')
            self.assertEqual(h.run_once(c,self.T+2),[])
            self.assertEqual(mk.run_once(c,self.T+2),[])
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            self.assertIsNone(h.agent_context(c,mid,'HERMES'))
            self.assertIsNone(mk.agent_context(c,mid,'HERMES'))
            self.assertEqual(self.counts(c),(1,2,1,1,1,0,0,0))

    def test_missing_benchmark_can_become_available_without_replacing_acquisition(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            did=h.run_once(c,self.T)[0]
            original=h.packet(c,did)
            self.assertEqual(original['product_demo']['status'],'unavailable')
            self.assertEqual(mk.run_once(c,self.T),[])
            self.assertEqual(mk.status(c)['drafts'][0]['state'],'unavailable')
            rid,result=self.benchmark_fixture(c,aid)
            self.assertEqual(h.run_once(c,self.T+1),[])
            self.assertEqual(h.packet(c,did),original)
            self.assertEqual(mk.run_once(c,self.T+1),[did])
            self.assertEqual(mk.packet(c,did)['payload']['facts']['laboratory_run'],rid)
            self.assertEqual(mk.run_once(c,self.T+2),[])
            self.assertEqual(self.counts(c),(1,1,1,1,1,0,0,0))
            self.assertEqual(s.used(c),10000)


if __name__=='__main__':
    unittest.main()
