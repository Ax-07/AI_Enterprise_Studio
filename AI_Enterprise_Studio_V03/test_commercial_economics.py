"""Commercial profitability arithmetic and existing offer revalidation."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import commercial as co
import serveur as s
from departments import commercial_economics as econ


class CommercialEconomicsTests(unittest.TestCase):
    def setUp(self):
        self.plan={'price_cents':10000,'signal_ids':[]}
        self.assumptions={'variable_cost_cents':4500,'fixed_month_cents':11000,
                          'monthly_units':10,'rationale':'Hypothèses synthétiques non vérifiées.'}

    def test_reference_case_and_historical_facade(self):
        expected={'contribution_cents':5500,'monthly_result_cents':44000,
                  'breakeven_units':2,'adverse_monthly_result_cents':12000,
                  'classification':'hypothèses EUR, avant impôt et coûts initiaux non inclus'}
        self.assertEqual(econ.economics_result(self.plan,self.assumptions),expected)
        self.assertEqual(co.economics_result(self.plan,self.assumptions),expected)

    def test_adverse_rounding_and_odd_volume(self):
        plan={'price_cents':100}
        d={'variable_cost_cents':31,'fixed_month_cents':100,'monthly_units':5}
        adverse=econ.adverse_parameters(plan,d)
        self.assertEqual(adverse['variable_cost_cents'],38)
        self.assertEqual(adverse['monthly_units'],2)
        self.assertEqual(adverse['breakeven_units'],2)
        result=econ.economics_result(plan,d)
        self.assertEqual(result['breakeven_units'],2)
        self.assertEqual(result['monthly_result_cents'],245)
        self.assertEqual(result['adverse_monthly_result_cents'],24)

    def test_minimum_volume_and_zero_fixed_cost(self):
        plan={'price_cents':100}
        d={'variable_cost_cents':0,'fixed_month_cents':0,'monthly_units':1}
        self.assertEqual(econ.adverse_parameters(plan,d)['monthly_units'],1)
        self.assertEqual(econ.adverse_parameters(plan,d)['breakeven_units'],0)
        self.assertEqual(econ.economics_result(plan,d)['breakeven_units'],0)
        self.assertEqual(econ.economics_result(plan,d)['adverse_monthly_result_cents'],100)

    def test_zero_negative_and_adverse_contribution(self):
        for cost in (100,101):
            d={'variable_cost_cents':cost,'fixed_month_cents':10,'monthly_units':4}
            r=econ.economics_result({'price_cents':100},d)
            self.assertIsNone(r['breakeven_units'])
            self.assertLess(r['monthly_result_cents'],0)
            self.assertIsNone(econ.adverse_parameters({'price_cents':100},d)['breakeven_units'])
        d={'variable_cost_cents':90,'fixed_month_cents':5,'monthly_units':4}
        r=econ.economics_result({'price_cents':100},d)
        self.assertEqual(r['breakeven_units'],1)
        self.assertEqual(r['monthly_result_cents'],35)
        self.assertEqual(r['adverse_monthly_result_cents'],-21)
        self.assertIsNone(econ.adverse_parameters({'price_cents':100},d)['breakeven_units'])

    def test_functions_do_not_mutate_inputs_and_callback_is_live(self):
        plan=dict(self.plan);d=dict(self.assumptions)
        econ.economics_result(self.plan,self.assumptions)
        econ.adverse_parameters(self.plan,self.assumptions)
        self.assertEqual(self.plan,plan)
        self.assertEqual(self.assumptions,d)
        with patch.object(econ,'economics_result',return_value={'fixture':True}) as calculate:
            self.assertEqual(co.economics_result(self.plan,self.assumptions),{'fixture':True})
            calculate.assert_called_once_with(self.plan,self.assumptions)


class CommercialEconomicsProjectionTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        self.plan={'price_cents':10000,'signal_ids':[]}
        self.d={'variable_cost_cents':4500,'fixed_month_cents':11000,'monthly_units':10}
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','terminée')").lastrowid
            self.pid=c.execute("INSERT INTO projects(origin,title) VALUES('fixture','Fixture')").lastrowid
            self.oid=c.execute('INSERT INTO commercial_offers(project,mission,plan) VALUES(?,?,?)',
                              (self.pid,self.mid,json.dumps(self.plan))).lastrowid
            c.execute('INSERT INTO commercial_economics(offer,mission,assumptions,result) VALUES(?,?,?,?)',
                      (self.oid,self.mid,json.dumps(self.d),json.dumps(co.economics_result(self.plan,self.d))))

    def offer(self,c):
        row=c.execute('SELECT * FROM commercial_offers WHERE id=?',(self.oid,)).fetchone()
        return co.offer_status(c,row)

    def test_projection_uses_adverse_parameters_without_writes(self):
        with s.db() as c:
            before=c.total_changes
            offer=self.offer(c)
            adverse=offer['economics']['adverse_parameters']
            self.assertEqual((adverse['variable_cost_cents'],adverse['monthly_units'],adverse['breakeven_units']),(5400,5,3))
            self.assertNotIn('scenario_economique_manquant_ou_defavorable',offer['gaps'])
            self.assertEqual(offer['sales'],0)
            self.assertFalse(offer['external_authorized'])
            self.assertEqual(c.total_changes,before)

    def test_tampered_result_is_not_accepted(self):
        with s.db() as c:
            tampered=co.economics_result(self.plan,self.d)
            tampered['monthly_result_cents']+=1
            c.execute('UPDATE commercial_economics SET result=? WHERE offer=?',(json.dumps(tampered),self.oid))
            offer=self.offer(c)
            self.assertIn('scenario_economique_manquant_ou_defavorable',offer['gaps'])
            self.assertEqual(offer['state'],'preparation_incomplete')
            self.assertFalse(offer['external_authorized'])


if __name__=='__main__':
    unittest.main()
