"""Portfolio cost attribution and separation of receipt modes."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import business
import portfolio
import serveur as s
from departments import accounting, receipt_accounting


class PortfolioFinanceTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        with s.db() as c:
            self.projects=[c.execute('INSERT INTO projects(origin,title,state) VALUES(?,?,?)',
                              ('fixture:'+state,state,state)).lastrowid
                           for state in ('active','paused','archived')]
            self.missions=[c.execute("INSERT INTO missions(title,mode,state) VALUES(?,'cloud','terminée')",
                              ('fixture '+str(i),)).lastrowid for i in range(5)]
            for mid,pid in zip(self.missions[:3],self.projects):
                portfolio.attach(c,mid,pid,'fixture')
            c.executemany('INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,?,?,?,?)',[
                (self.missions[0],'fixture',1000,120,'mesuré'),
                (self.missions[0],'fixture',900,0,'mesuré'),
                (self.missions[1],'fixture',300,None,'à rapprocher'),
                (self.missions[2],'fixture',700,None,'réservé'),
                (self.missions[3],'fixture',80,100,'mesuré'),
                (self.missions[4],'fixture',200,None,'à rapprocher'),
                (None,'fixture',60,None,'réservé')])

    def test_all_project_states_and_unallocated_partition(self):
        with s.db() as c:
            totals=[accounting.project_total(c,p) for p in self.projects]
            self.assertEqual(totals,[120,300,700])
            self.assertEqual(accounting.unallocated_total(c),360)
            self.assertEqual(accounting.global_total(c),1480)
            self.assertEqual(sum(totals)+accounting.unallocated_total(c),s.used(c))
            self.assertEqual(accounting.project_total(c,999999),0)

    def test_real_portfolio_projection_preserves_amounts(self):
        with s.db() as c:
            before=c.total_changes
            result=portfolio.status(c)
            self.assertEqual([p['spent'] for p in result['projects']],[120,300,700])
            self.assertEqual(result['unallocated'],360)
            self.assertEqual(c.total_changes,before)

    def test_attribution_cannot_double_charge_and_rollback_is_visible(self):
        with s.db() as c:
            with self.assertRaisesRegex(ValueError,'déjà attribuée'):
                portfolio.attach(c,self.missions[0],self.projects[1],'fixture')
            portfolio.attach(c,self.missions[0],self.projects[0],'fixture')
            self.assertEqual(accounting.project_total(c,self.projects[0]),120)
        with self.assertRaisesRegex(RuntimeError,'fixture rollback'):
            with s.db() as c:
                portfolio.attach(c,self.missions[3],self.projects[0],'fixture')
                self.assertEqual(accounting.project_total(c,self.projects[0]),220)
                self.assertEqual(accounting.unallocated_total(c),260)
                self.assertEqual(accounting.global_total(c),1480)
                raise RuntimeError('fixture rollback')
        with s.db() as c:
            self.assertEqual(accounting.project_total(c,self.projects[0]),120)
            self.assertEqual(accounting.unallocated_total(c),360)

    def test_ledger_projection_is_read_only(self):
        with s.db() as c:
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                self.assertEqual(accounting.project_total(c,self.projects[1]),300)
                self.assertEqual(accounting.unallocated_total(c),360)
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')


class ReceiptAccountingTests(unittest.TestCase):
    def test_modes_payment_and_refund_are_separate(self):
        records=[{'mode':'test','kind':'payment','amount_cents':1000},
                 {'mode':'test','kind':'refund','amount_cents':300},
                 {'mode':'owner_declared_live','kind':'payment','amount_cents':2500},
                 {'mode':'owner_declared_live','kind':'refund','amount_cents':500},
                 {'mode':'unknown','kind':'payment','amount_cents':9999},
                 {'mode':'test','kind':'other','amount_cents':8888}]
        original=[dict(r) for r in records]
        self.assertEqual(receipt_accounting.totals(records),{
            'test':{'gross_cents':1000,'refunds_cents':300,'net_cents':700},
            'owner_declared_live':{'gross_cents':2500,'refunds_cents':500,'net_cents':2000}})
        self.assertEqual(records,original)

    def test_empty_and_refund_only_preserve_historical_math(self):
        zeros={'gross_cents':0,'refunds_cents':0,'net_cents':0}
        self.assertEqual(receipt_accounting.totals([]),{'test':zeros,'owner_declared_live':zeros})
        self.assertEqual(receipt_accounting.totals([
            {'mode':'test','kind':'refund','amount_cents':12}])['test']['net_cents'],-12)

    def test_business_projection_never_claims_verified_revenue(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(s,'DB',Path(directory)/'fixture.sqlite3'):
                s.init()
                with s.db() as c:
                    totals={'test':{'gross_cents':100,'refunds_cents':0,'net_cents':100},
                            'owner_declared_live':{'gross_cents':200,'refunds_cents':0,'net_cents':200}}
                    with patch.object(receipt_accounting,'totals',return_value=totals) as compute:
                        before=c.total_changes
                        result=business.status(c,t=0)
                        compute.assert_called_once_with([])
                        self.assertEqual(result['totals'],totals)
                        self.assertEqual(result['currency'],'EUR')
                        self.assertEqual(result['verified_live_cents'],0)
                        self.assertFalse(result['verified_live_available'])
                        self.assertFalse(result['external_authorized'])
                        self.assertEqual(c.total_changes,before)


if __name__=='__main__':
    unittest.main()
