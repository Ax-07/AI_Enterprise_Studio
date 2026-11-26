import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools as t
import intelligence as intel

class CampusEconomyTests(unittest.TestCase):
    def test_economy_read_only(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            s.init()
            with s.db() as db:
                mid=db.execute("INSERT INTO missions(title,mode,state) VALUES('Étude','cloud','terminée')").lastrowid
                demo=db.execute("INSERT INTO missions(title,mode,state) VALUES('Simulation','demo','terminée')").lastrowid
                db.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',1000,500,'mesuré')",(mid,))
                db.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'test',2000,'réservé')",(demo,))
                # Synthetic projection records; not real receipts or offers.
                for ref,mode,kind,amount in [('test-payment','test','payment',1200),('test-refund','test','refund',200),('declared','owner_declared_live','payment',3000)]:
                    db.execute("INSERT INTO business_receipts(offer,reference_hash,mode,kind,amount_cents,occurred_at,recorded_at) VALUES(1,?,?,?,?,1,1)",(ref,mode,kind,amount))
                dct={'price_cents':1000,'variable_cost_cents':400,'fixed_month_cents':1200,'monthly_units':5,
                    'automation_pct':60,'risk':3,'source_runs':[],'rationale':'PRIVATE_RATIONALE hypothèse économique non validée.'}
                ids=[]
                for mission in (mid,demo):
                    oid=db.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,'Piste','Hypothèse','Test')",(mission,)).lastrowid
                    intel.assess(db,mission,'MIDAS',str(oid),json.dumps(dct))
                    ids.append(oid)
            before=s.DB.read_bytes()
            def read():return t.read(s.DB,'economy',{},resources={'budget':4000000,'key':'PRIVATE_KEY'})
            with patch.object(s,'request',side_effect=AssertionError('No provider')) as network:
                r=read();network.assert_not_called()
            self.assertTrue(r['read_only'])
            self.assertEqual(r['limit'],31)
            summary,simulation,cloud=r['rows']
            self.assertEqual(summary['committed'],2500)
            self.assertEqual(summary['remaining'],3997500)
            self.assertEqual(summary['receipts']['test']['net_cents'],1000)
            self.assertEqual(summary['receipts']['owner_declared_live']['net_cents'],3000)
            self.assertIsNone(summary['verified_revenue_cents'])
            self.assertIsNone(summary['actual_profit_cents'])
            self.assertFalse(summary['investment_authorized'])
            self.assertFalse(simulation['comparable'])
            self.assertTrue(cloud['comparable'])
            self.assertEqual(cloud['scenario']['result']['monthly_result_cents'],1800)
            self.assertEqual(cloud['scenario']['result']['breakeven_units'],2)
            self.assertNotIn('PRIVATE',json.dumps(r))
            self.assertEqual(s.DB.read_bytes(),before)
            with self.assertRaises(t.BadQuery):t.read(s.DB,'economy',{'invest':['true']})
            with s.db() as db:db.execute("UPDATE opportunities SET body='Modifié' WHERE id=?",(ids[0],))
            self.assertIsNone(read()['rows'][2]['scenario'])
            with s.db() as db:db.execute("UPDATE market_assessments SET result='{}' WHERE opportunity=?",(ids[1],))
            self.assertIsNone(read()['rows'][1]['scenario'])
