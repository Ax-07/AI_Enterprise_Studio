"""Budget adaptation compatibility and transaction boundaries, entirely offline."""
import sqlite3
import unittest
from unittest.mock import patch

import autopilot
import budgeting


class BudgetEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE ledger(id INTEGER PRIMARY KEY,mission INTEGER,reserved INTEGER,actual INTEGER);
            CREATE TABLE events(mission INTEGER,task INTEGER,action TEXT,ok INTEGER);
            CREATE TABLE campaign_missions(campaign INTEGER,mission INTEGER);
            INSERT INTO campaign_missions VALUES(10,1),(10,2),(20,3);
        """)
        budgeting.init(self.c)
        self.c.commit()
        self.cfg={'budget':100000,'mission_budget':100000,'call_limit':10}
        self.campaign={'id':10,'budget':100000}
        self.mid=1
        self.stage=7
        self.pi,self.po=1,2

    def body(self,n):
        return {'input':'Économie fixture','max_output_tokens':n}

    def estimate(self,n,requested=4096):
        return budgeting.estimate(self.body(requested),self.pi,self.po,n)

    def fit(self,agent='ORION',requested=4096,used=0,cfg=None,campaign=None):
        return budgeting.fit(self.c,self.mid,self.stage,agent,self.body(requested),
                             self.pi,self.po,self.cfg if cfg is None else cfg,
                             used,self.campaign if campaign is None else campaign)

    def latest(self):
        return budgeting.history(self.c,self.mid)[0]

    def test_full_fit_and_exact_boundary(self):
        reserve=self.estimate(4096)
        cfg=dict(self.cfg,budget=reserve)
        self.assertEqual(self.fit(cfg=cfg),(4096,reserve,None))
        row=self.latest()
        self.assertEqual(row['decision'],'unchanged')
        self.assertEqual(row['limits'],{'global':reserve,'mission':100000,'campaign':100000})
        self.assertEqual(row['requested_reserve'],reserve)
        self.assertEqual(row['chosen_reserve'],reserve)

    def test_binary_search_maximum_affordable_tokens(self):
        ceiling=self.estimate(1500)
        cfg=dict(self.cfg,mission_budget=ceiling)
        self.assertEqual(self.fit(cfg=cfg),(1500,ceiling,None))
        self.assertGreater(self.estimate(1501),ceiling)
        self.assertEqual(self.latest()['decision'],'adapted')
        self.assertEqual(self.latest()['available'],ceiling)

    def test_measured_and_unconfirmed_costs_across_envelopes(self):
        self.c.executemany('INSERT INTO ledger(mission,reserved,actual) VALUES(?,?,?)',
                           [(1,700,0),(1,300,None),(1,500,100),(2,900,None),(3,600,None)])
        self.assertEqual(autopilot.costs(self.c,10),1300)
        cfg=dict(self.cfg,budget=50000,mission_budget=6000)
        campaign={'id':10,'budget':6000}
        chosen,reserve,error=self.fit(used=1900,cfg=cfg,campaign=campaign)
        self.assertIsNone(error)
        row=self.latest()
        self.assertEqual(row['limits'],{'global':48100,'mission':5600,'campaign':4700})
        self.assertEqual(row['available'],4700)
        self.assertLessEqual(reserve,4700)
        self.assertGreater(self.estimate(chosen+1),4700)

    def test_refusal_below_minimum_and_deterministic_tie(self):
        floor=self.estimate(1024)
        limit=floor-1
        for cfg,campaign,reason in [
            (dict(self.cfg,budget=limit),{'id':10,'budget':100000},'Budget logiciel'),
            (dict(self.cfg,mission_budget=limit),{'id':10,'budget':100000},'Budget de mission'),
            (self.cfg,{'id':10,'budget':limit},'Enveloppe Autopilote'),
            (dict(self.cfg,budget=limit,mission_budget=limit),{'id':10,'budget':limit},'Budget logiciel')]:
            with self.subTest(reason=reason):
                chosen,reserve,error=self.fit(cfg=cfg,campaign=campaign)
                self.assertIsNone(chosen)
                self.assertIsNone(reserve)
                self.assertTrue(error.startswith(reason))
                self.assertIn('aucun appel envoyé',error)
                row=self.latest()
                self.assertEqual(row['decision'],'refused')
                self.assertEqual(row['minimum_reserve'],floor)
                self.assertIsNone(row['chosen_reserve'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)

    def test_agent_preferences_and_draft_scope(self):
        self.assertEqual(self.fit(agent='ATLAS')[0],2048)
        self.assertEqual(self.latest()['preferred_tokens'],2048)
        self.assertEqual(self.fit(agent='ATLAS',requested=8192)[0],8192)
        self.c.executemany('INSERT INTO events VALUES(?,?,?,?)',
                           [(2,7,'write_file',1),(1,8,'write_file',1),(1,7,'write_file',0)])
        self.assertEqual(self.fit(agent='NEXUS',requested=8192)[0],8192)
        self.c.execute("INSERT INTO events VALUES(1,7,'write_file',1)")
        self.assertEqual(self.fit(agent='NEXUS',requested=8192)[0],2048)
        self.assertEqual(self.fit(agent='NEXUS',requested=4096)[0],4096)

    def test_small_requested_limit_preserves_minimum(self):
        reserve=self.estimate(100,requested=100)
        self.assertEqual(self.fit(requested=100,cfg=dict(self.cfg,budget=reserve)),(100,reserve,None))
        self.assertEqual(self.latest()['minimum_reserve'],reserve)

    def test_call_limit_refuses_before_campaign_lookup_or_decision(self):
        self.c.execute('INSERT INTO ledger(mission,reserved,actual) VALUES(1,10,0)')
        with patch.object(autopilot,'costs',side_effect=AssertionError('unexpected campaign lookup')) as costs:
            with self.assertRaisesRegex(RuntimeError,'Plafond des appels IA'):
                self.fit(cfg=dict(self.cfg,call_limit=1))
            costs.assert_not_called()
        self.assertEqual(budgeting.history(self.c,self.mid),[])

    def test_caller_owns_transaction_and_live_callbacks(self):
        self.c.commit()
        with self.assertRaisesRegex(RuntimeError,'fixture rollback'):
            with self.c:
                with patch.object(autopilot,'costs',return_value=1000) as costs:
                    with patch.object(budgeting,'estimate',wraps=budgeting.estimate) as estimate:
                        self.fit()
                        costs.assert_called_once_with(self.c,10)
                        self.assertGreater(estimate.call_count,2)
                        self.assertEqual(self.latest()['limits']['campaign'],99000)
                raise RuntimeError('fixture rollback')
        self.assertEqual(budgeting.history(self.c,self.mid),[])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
