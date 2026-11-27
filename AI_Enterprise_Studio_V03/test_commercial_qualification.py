"""Qualification contracts on a temporary real server database."""
import copy
import json
import unittest
from unittest.mock import patch

import business as b
import commercial as co
import serveur as s
import test_business as tb
from departments import commercial_qualification as cq

class CommercialQualificationTests(unittest.TestCase):
    setUp=tb.BusinessTests.setUp
    start=tb.BusinessTests.start
    historical=tb.BusinessTests.historical
    prepare=tb.BusinessTests.prepare
    fixture=tb.BusinessTests.fixture
    T=tb.BusinessTests.T

    def offer(self,c,oid):
        return co.offer_status(c,b.offer_row(c,oid))

    def test_documentary_gaps_allow_observation_only_not_sale(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=b.offer_row(c,oid)
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                v,eligible,reasons=b.gate(c,row)
                self.assertTrue(eligible)
                self.assertEqual(reasons,['indices_documentaires_insuffisants','revue_independante_manquante_ou_reserves'])
                self.assertEqual(v['state'],'preparation_incomplete')
                self.assertFalse(v['external_authorized'])
                self.assertEqual((v['sales'],v['observations'],v['commercial_spend_cents']),(0,0,0))
                status=b.status(c,self.T)
                self.assertFalse(status['catalog'][0]['sale_authorized'])
                self.assertEqual(status['trials'],[])
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')

    def test_independent_audit_failure_overrides_success(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=c.execute('SELECT mission,result FROM verification_results WHERE artifact=?',(aid,)).fetchone()
            result=json.loads(row['result']);result['status']='failed'
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL','{}',?)",
                      (aid,row['mission'],json.dumps(result)))
            v,eligible,reasons=b.gate(c,b.offer_row(c,oid))
            self.assertFalse(eligible)
            self.assertIn('preuve_technique_independante_manquante',reasons)

    def test_changed_product_and_required_laboratory_block(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            c.execute("UPDATE artifacts SET name='audit_catalogue.html' WHERE id=?",(aid,))
            self.assertIn('preuve_technique_independante_manquante',self.offer(c,oid)['gaps'])
            self.assertFalse(b.gate(c,b.offer_row(c,oid))[1])
            c.execute("UPDATE artifacts SET name='corrige.csv',content=content||' ' WHERE id=?",(aid,))
            v=self.offer(c,oid)
            self.assertEqual(v['technical_proofs'],[])
            self.assertIn('preuve_technique_independante_manquante',v['gaps'])

    def test_economics_recomputed_not_trusted(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=c.execute('SELECT assumptions,result FROM commercial_economics WHERE offer=?',(oid,)).fetchone()
            result=json.loads(row['result']);result['monthly_result_cents']+=1
            c.execute('UPDATE commercial_economics SET result=? WHERE offer=?',(json.dumps(result),oid))
            self.assertIn('scenario_economique_manquant_ou_defavorable',self.offer(c,oid)['gaps'])
            self.assertFalse(b.gate(c,b.offer_row(c,oid))[1])
            plan=self.offer(c,oid)['plan'];assumptions=json.loads(row['assumptions'])
            assumptions['variable_cost_cents']=plan['price_cents']+1
            c.execute('UPDATE commercial_economics SET assumptions=?,result=? WHERE offer=?',
                      (json.dumps(assumptions),json.dumps(co.economics_result(plan,assumptions)),oid))
            self.assertIn('scenario_economique_manquant_ou_defavorable',self.offer(c,oid)['gaps'])
            self.assertFalse(b.gate(c,b.offer_row(c,oid))[1])

    def test_inactive_or_replaced_offer_not_eligible(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=b.offer_row(c,oid)
            c.execute("UPDATE projects SET state='paused' WHERE id=?",(pid,))
            v,eligible,reasons=b.gate(c,row)
            self.assertFalse(eligible);self.assertIn('activité inactive',reasons)
            c.execute("UPDATE projects SET state='active' WHERE id=?",(pid,))
            with patch.object(co,'project_status',return_value={'offer':{'id':oid+1}}):
                v,eligible,reasons=b.gate(c,row)
                self.assertFalse(eligible);self.assertIn('offre remplacée',reasons)

    def test_review_revise_and_unfinished_mission_block(self):
        oid,aid,pid=self.fixture(review='revise')
        with s.db() as c:
            row=b.offer_row(c,oid)
            self.assertFalse(b.gate(c,row)[1])
            c.execute("UPDATE missions SET state='en cours' WHERE id=?",(row['mission'],))
            v=co.offer_status(c,row)
            self.assertIn('mission_non_terminee',v['gaps'])
            self.assertEqual(v['state'],'preparation_incomplete')

    def test_frozen_snapshot_exact_fields_and_hash_changes(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            v=self.offer(c,oid)
            frozen=b.frozen(v)
            self.assertEqual(set(frozen),{'id','project','mission','artifact','artifact_sha256','plan','economics','review','gaps','state'})
            changed=copy.deepcopy(v);changed['observations']=99
            self.assertEqual(b.digest(b.frozen(changed)),b.digest(frozen))
            changed['plan']['price_cents']+=1
            self.assertNotEqual(b.digest(b.frozen(changed)),b.digest(frozen))

    def test_live_facades_preserve_callbacks_and_limits(self):
        oid,aid,pid=self.fixture()
        with s.db() as c:
            row=b.offer_row(c,oid)
            with patch.object(cq,'offer_status',return_value={'fixture':True}) as status:
                self.assertEqual(co.offer_status(c,row),{'fixture':True})
                status.assert_called_once_with(c,row,intel=co.intel,signal=co._signal,research=co.research,
                    portfolio=co.portfolio,hashlib=co.hashlib,urlsplit=co.urlsplit,
                    commercial_economics=co.commercial_economics,economics_result=co.economics_result,limit=co.LIMIT)
            with patch.object(cq,'gate',return_value=({'fixture':True},False,[])) as gate:
                self.assertEqual(b.gate(c,row),({'fixture':True},False,[]))
                gate.assert_called_once_with(c,row,commercial=b.commercial,portfolio=b.portfolio)


if __name__=='__main__':
    unittest.main()
