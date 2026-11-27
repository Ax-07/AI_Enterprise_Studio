"""Ledger projection contracts: exact historical scopes and read-only access."""
import sqlite3
import unittest
from unittest.mock import patch

import autopilot
import serveur as s
from departments import accounting


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE ledger(id INTEGER PRIMARY KEY,mission INTEGER,model TEXT,reserved INTEGER,actual INTEGER,state TEXT);
            CREATE TABLE campaign_missions(campaign INTEGER,mission INTEGER UNIQUE);
            INSERT INTO campaign_missions VALUES(10,1),(10,2),(20,3);
        """)
        self.c.commit()

    def seed(self):
        self.c.executemany('INSERT INTO ledger(mission,reserved,actual,state) VALUES(?,?,?,?)',[
            (1,1000,120,'mesuré'),(1,900,0,'mesuré'),(1,300,None,'à rapprocher'),
            (2,700,None,'réservé'),(3,80,100,'mesuré'),(4,200,None,'à rapprocher'),
            (None,60,None,'réservé'),(1,None,None,'historique')])

    def test_empty_and_unknown_scopes(self):
        self.assertEqual(accounting.global_total(self.c),0)
        self.assertEqual(tuple(accounting.mission_totals(self.c,1)),(0,0))
        self.assertEqual(accounting.campaign_total(self.c,10),0)
        self.seed()
        self.assertEqual(tuple(accounting.mission_totals(self.c,999)),(0,0))
        self.assertEqual(accounting.campaign_total(self.c,999),0)

    def test_actual_precedence_zero_and_pending_reservations(self):
        self.seed()
        self.assertEqual(tuple(accounting.mission_totals(self.c,1)),(420,4))
        self.assertEqual(accounting.global_total(self.c),1480)
        self.assertEqual(accounting.campaign_total(self.c,10),1120)

    def test_scope_partition_without_double_counting(self):
        self.seed()
        self.assertEqual(accounting.campaign_total(self.c,20),100)
        self.assertEqual(tuple(accounting.mission_totals(self.c,4)),(200,1))
        self.assertEqual(accounting.global_total(self.c),
                         accounting.campaign_total(self.c,10)+accounting.campaign_total(self.c,20)+200+60)
        self.assertEqual(tuple(accounting.mission_totals(self.c,None)),(0,0))

    def test_historical_sql_equivalence(self):
        self.seed()
        old=self.c.execute('SELECT COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE actual END),0) FROM ledger').fetchone()[0]
        self.assertEqual(accounting.global_total(self.c),old)
        for mid in (1,2,3,4,None,999):
            expected=self.c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()
            self.assertEqual(tuple(accounting.mission_totals(self.c,mid)),tuple(expected))

    def test_read_only_and_transaction_visibility(self):
        self.seed()
        self.c.commit()
        before=self.c.total_changes
        self.c.execute('PRAGMA query_only=ON')
        self.assertEqual(accounting.global_total(self.c),1480)
        self.assertEqual(accounting.campaign_total(self.c,10),1120)
        self.assertEqual(tuple(accounting.mission_totals(self.c,1)),(420,4))
        self.assertEqual(self.c.total_changes,before)
        self.assertFalse(self.c.in_transaction)
        self.c.execute('PRAGMA query_only=OFF')
        self.c.execute('UPDATE ledger SET actual=50 WHERE mission=2')
        self.assertEqual(accounting.campaign_total(self.c,10),470)
        self.assertTrue(self.c.in_transaction)
        self.c.rollback()
        self.assertEqual(accounting.campaign_total(self.c,10),1120)

    def test_facades_preserved_and_live_delegation(self):
        self.seed()
        self.assertEqual(s.used(self.c),1480)
        self.assertEqual(autopilot.costs(self.c,10),1120)
        with patch.object(accounting,'global_total',return_value=17) as total:
            self.assertEqual(s.used(self.c),17)
            total.assert_called_once_with(self.c)
        with patch.object(accounting,'campaign_total',return_value=23) as total:
            self.assertEqual(autopilot.costs(self.c,10),23)
            total.assert_called_once_with(self.c,10)


if __name__=='__main__':
    unittest.main()
