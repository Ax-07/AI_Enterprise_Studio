"""D06.1: reuse existing commercial fixtures and evidence, never activate channels."""
import json
import unittest
from unittest.mock import patch
import serveur as s
import campus_tools as tools
import business as b
import acquisition as ac
import hermes_acquisition as h
import marketing as mk
import test_marketing as tm

class CampusCommercialTests(unittest.TestCase):
    setUp=tm.MarketingTests.setUp
    start=tm.MarketingTests.start
    historical=tm.MarketingTests.historical
    prepare=tm.MarketingTests.prepare
    fixture=tm.MarketingTests.fixture
    benchmark_fixture=tm.MarketingTests.benchmark_fixture
    T=tm.MarketingTests.T
    def test_commercial_projection_and_stale_evidence(self):
        oid,aid,pid=self.fixture()
        with s.db() as db:
            rid,_=self.benchmark_fixture(db,aid)
            did=h.run_once(db,self.T)[0]
            mk.run_once(db,self.T)
            for i,mode in enumerate(('test','owner_declared_live')):
                db.execute("INSERT INTO business_receipts(offer,reference_hash,mode,kind,amount_cents,occurred_at,recorded_at) VALUES(?,?,?,'payment',4900,?,?)",(oid,'private-hash-'+str(i),mode,self.T,self.T))
        before=s.DB.read_bytes()
        def read(tool,**params):
            return tools.read(s.DB,tool,{k:[str(v)] for k,v in params.items()})['rows']
        with patch.object(s,'request',side_effect=AssertionError('Network forbidden')) as network:
            result=read('business')
            self.assertFalse(result[0]['verified_live_available'])
            self.assertIsNone(result[0]['verified_live_cents'])
            self.assertEqual(result[0]['totals']['test']['net_cents'],4900)
            self.assertEqual(result[0]['totals']['owner_declared_live']['net_cents'],4900)
            self.assertNotIn('private-hash',json.dumps(result))
            self.assertEqual(read('marketing')[0]['id'],did)
            packet=read('marketing_detail',id=did)[0]
            self.assertEqual(packet['state'],'technical_pass')
            self.assertFalse(packet['publication_authorized'])
            self.assertFalse(packet['video_generated'])
            self.assertTrue(packet['content']['youtube']['storyboard'])
            self.assertEqual(read('hermes_detail',id=did)[0]['state'],'internal_ready')
            self.assertEqual(before,s.DB.read_bytes())
            with s.db() as db:ac.revoke(db,{'confirm':True,'draft':did},self.T+1)
            revoked=read('marketing_detail',id=did)[0]
            self.assertEqual(revoked['state'],'unavailable')
            self.assertIsNone(revoked['content'])
            network.assert_not_called()
