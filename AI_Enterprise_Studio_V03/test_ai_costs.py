"""Cost formula and ledger compatibility on synthetic provider responses."""
from contextlib import ExitStack
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import budgeting
import moteur as m
import serveur as s
from departments import ai_costs
from infrastructure import providers


class CostArithmeticTests(unittest.TestCase):
    def test_reservation_matches_historical_formula_with_unicode(self):
        for body in ({'input':'ASCII','max_output_tokens':4096},
                     {'input':'Économie 🌍','max_output_tokens':4096},
                     {'input':'a','text':{'schema':{'type':'object'}},'max_output_tokens':9}):
            for pi,po in s.PRICES.values():
                with self.subTest(body=body,pi=pi,po=po):
                    n=body['max_output_tokens']
                    expected=math.ceil((len(json.dumps(body,ensure_ascii=False).encode())+1024)*pi+n*po)
                    self.assertEqual(ai_costs.reservation(body,pi,po,n),expected)
                    self.assertEqual(budgeting.estimate(body,pi,po,n),expected)

    def test_adapted_estimate_serializes_chosen_output_limit_without_mutating(self):
        body={'input':'Économie','max_output_tokens':8192}
        for n in (9,10,999,1000,1024,2048,8192):
            replacement={**body,'max_output_tokens':n}
            expected=math.ceil((len(json.dumps(replacement,ensure_ascii=False).encode())+1024)*0.1+n*0.5)
            self.assertEqual(budgeting.estimate(body,0.1,0.5,n),expected)
        self.assertEqual(body,{'input':'Économie','max_output_tokens':8192})

    def test_measured_rounds_once_and_retains_zero_usage(self):
        for it,ot in [(0,0),(1,1),(7,11),(100,20),(12345,6789)]:
            for pi,po in s.PRICES.values():
                self.assertEqual(ai_costs.measured(it,ot,pi,po),math.ceil(it*pi+ot*po))
        self.assertEqual(ai_costs.measured(1,1,0.1,0.5),1)
        self.assertEqual(ai_costs.measured(0,0,0.1,0.5),0)

    def test_estimate_resolves_existing_serializer_and_rounder(self):
        body={'max_output_tokens':8192}
        with patch.object(budgeting.json,'dumps',return_value='é') as serialize:
            with patch.object(budgeting.math,'ceil',return_value=123) as ceil:
                self.assertEqual(budgeting.estimate(body,0.1,0.5,2048),123)
                serialize.assert_called_once_with({'max_output_tokens':2048},ensure_ascii=False)
                ceil.assert_called_once_with((2+1024)*0.1+2048*0.5)


class CostLedgerTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        self.request=self.stack.enter_context(patch.object(s,'request',side_effect=AssertionError('unexpected transport')))
        self.stack.enter_context(patch.object(providers.urllib.request,'urlopen',side_effect=AssertionError('unexpected network')))
        s.init()
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','en cours')").lastrowid
            self.tid=m.add_task(c,self.mid,'ORION','Fixture')
        self.model=next(iter(s.PRICES))
        self.pi,self.po=s.PRICES[self.model]
        self.cfg={'models':{'ORION':self.model},'key':'fixture-key','budget':1000000,
                  'mission_budget':1000000,'call_limit':10}

    def rows(self):
        with s.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM ledger WHERE mission=? ORDER BY id',(self.mid,))]

    def invoke(self):
        return s.call_model(self.mid,'ORION','Économie',self.cfg,maxout=2048,
                            stage=self.tid,schema=m.SCHEMA,validator=lambda value: value=={})

    def test_reservation_precedes_transport_and_measured_cost_matches(self):
        def reply(url,headers,body):
            row,=self.rows()
            self.assertEqual(row['state'],'réservé')
            self.assertIsNone(row['actual'])
            self.assertEqual(row['reserved'],math.ceil((len(json.dumps(body,ensure_ascii=False).encode())+1024)*self.pi+2048*self.po))
            self.assertEqual(row['limit_out'],2048)
            return {'status':'completed','usage':{'input_tokens':101,'output_tokens':21},
                    'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]}
        self.request.side_effect=reply
        self.assertEqual(self.invoke(),{})
        row,=self.rows()
        self.assertEqual(row['state'],'mesuré')
        self.assertEqual(row['actual'],math.ceil(101*self.pi+21*self.po))
        with s.db() as c:
            self.assertEqual(s.used(c),row['actual'])
        self.request.assert_called_once()

    def test_transport_failure_retains_reservation(self):
        self.request.side_effect=TimeoutError('fixture')
        with self.assertRaisesRegex(RuntimeError,'réservation conservée'):
            self.invoke()
        row,=self.rows()
        self.assertEqual(row['state'],'à rapprocher')
        self.assertIsNone(row['actual'])
        self.assertGreater(row['reserved'],0)
        with s.db() as c:
            self.assertEqual(s.used(c),row['reserved'])

    def test_zero_budget_refuses_before_transport_or_ledger_write(self):
        self.cfg['budget']=0
        with self.assertRaisesRegex(RuntimeError,'Budget logiciel insuffisant'):
            self.invoke()
        self.request.assert_not_called()
        self.assertEqual(self.rows(),[])


if __name__=='__main__':
    unittest.main()
