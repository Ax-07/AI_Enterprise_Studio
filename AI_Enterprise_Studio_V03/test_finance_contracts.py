"""Transverse finance contracts on real temporary SQLite with synthetic provider."""
from contextlib import ExitStack
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import autopilot
import budgeting
import business
import commercial
import moteur as m
import portfolio
import serveur as s
from departments import accounting
from infrastructure import providers


class FinanceFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        self.request=self.stack.enter_context(patch.object(s,'request',side_effect=AssertionError('unexpected transport')))
        self.stack.enter_context(patch.object(providers.urllib.request,'urlopen',side_effect=AssertionError('unexpected network')))
        s.init()
        self.model=max(s.PRICES,key=lambda name:s.PRICES[name][1])
        self.pi,self.po=s.PRICES[self.model]
        self.cfg={'models':{'ORION':self.model},'key':'fixture-key','budget':1000000,
                  'mission_budget':1000000,'call_limit':10}
        self.prompt='Évaluation financière fictive'
        self.rules='Fixture only'
        self.body=providers.responses_payload(self.model,self.prompt,4096,s.RULES,s.SCHEMA,
                                             schema=m.SCHEMA,rules=self.rules)
        self.cap=budgeting.estimate(self.body,self.pi,self.po,1500)
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','en cours')").lastrowid
            self.old=c.execute("INSERT INTO missions(title,mode,state) VALUES('previous','cloud','terminée')").lastrowid
            self.tid=m.add_task(c,self.mid,'ORION','Fixture')
            self.pid=c.execute("INSERT INTO projects(origin,title) VALUES('fixture','Fixture')").lastrowid
            portfolio.attach(c,self.mid,self.pid,'fixture')
            portfolio.attach(c,self.old,self.pid,'fixture')
            self.cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES(?,?,?,?,?,'actif')",
                               ('fixture',self.cap+300,2,json.dumps(dict.fromkeys(autopilot.FLAGS,True)),0)).lastrowid
            c.executemany("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'market')",
                          [(self.cid,self.mid),(self.cid,self.old)])
            c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,? ,300,'à rapprocher')",(self.old,self.model))
            c.execute("INSERT INTO ledger(model,reserved,actual,state) VALUES(?,200,100,'mesuré')",(self.model,))

    def invoke(self):
        return s.call_model(self.mid,'ORION',self.prompt,self.cfg,maxout=4096,
                            stage=self.tid,schema=m.SCHEMA,rules=self.rules,validator=lambda v:v=={})

    def reply(self,url,headers,body):
        self.assertEqual(body['max_output_tokens'],1500)
        with s.db() as c:
            decision=budgeting.history(c,self.mid)[0]
            self.assertEqual(decision['decision'],'adapted')
            self.assertEqual(decision['available'],self.cap)
            self.assertEqual(decision['chosen_reserve'],self.cap)
            row=c.execute('SELECT * FROM ledger WHERE mission=?',(self.mid,)).fetchone()
            self.assertEqual(row['state'],'réservé')
            self.assertIsNone(row['actual'])
            self.assertEqual(row['reserved'],math.ceil((len(json.dumps(body,ensure_ascii=False).encode())+1024)*self.pi+1500*self.po))
            self.assertEqual(autopilot.costs(c,self.cid),self.cap+300)
            self.assertEqual(accounting.project_total(c,self.pid),self.cap+300)
        return {'status':'completed','usage':{'input_tokens':100,'output_tokens':20},
                'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]}

    def test_adapted_call_reconciles_across_all_cost_scopes(self):
        self.request.side_effect=self.reply
        self.assertEqual(self.invoke(),{})
        measured=math.ceil(100*self.pi+20*self.po)
        with s.db() as c:
            self.assertEqual(tuple(accounting.mission_totals(c,self.mid)),(measured,1))
            self.assertEqual(autopilot.costs(c,self.cid),300+measured)
            self.assertEqual(accounting.project_total(c,self.pid),300+measured)
            self.assertEqual(accounting.unallocated_total(c),100)
            self.assertEqual(s.used(c),400+measured)
            projected=portfolio.status(c)
            self.assertEqual(projected['projects'][0]['spent'],300+measured)
            self.assertEqual(projected['unallocated'],100)
        self.request.assert_called_once()

    def test_unconfirmed_call_exhausts_campaign_and_next_call_is_refused(self):
        self.request.side_effect=TimeoutError('fixture only')
        with self.assertRaisesRegex(RuntimeError,'réservation conservée'):
            self.invoke()
        with s.db() as c:
            self.assertEqual(autopilot.costs(c,self.cid),self.cap+300)
            self.assertEqual(accounting.project_total(c,self.pid),self.cap+300)
            self.assertEqual(s.used(c),self.cap+400)
        with self.assertRaisesRegex(RuntimeError,'Enveloppe Autopilote insuffisant'):
            self.invoke()
        self.request.assert_called_once()
        with s.db() as c:
            row,=c.execute('SELECT state,actual,reserved FROM ledger WHERE mission=?',(self.mid,)).fetchall()
            self.assertEqual(tuple(row),('à rapprocher',None,self.cap))
            decisions=budgeting.history(c,self.mid)
            self.assertEqual([x['decision'] for x in decisions],['refused','adapted'])
            self.assertEqual(decisions[0]['available'],0)

    def offer(self,c):
        plan={'price_cents':10000,'signal_ids':[]}
        assumptions={'variable_cost_cents':4500,'fixed_month_cents':11000,'monthly_units':10}
        result=commercial.economics_result(plan,assumptions)
        oid=c.execute('INSERT INTO commercial_offers(project,mission,plan) VALUES(?,?,?)',
                      (self.pid,self.old,json.dumps(plan))).lastrowid
        c.execute('INSERT INTO commercial_economics(offer,mission,assumptions,result) VALUES(?,?,?,?)',
                  (oid,self.old,json.dumps(assumptions),json.dumps(result)))
        return oid

    def receipt(self,c,oid,reference,mode,kind,amount,parent=None):
        return business.receipt(c,{'offer':oid,'reference':reference,'mode':mode,'kind':kind,
                                   'parent':parent,'amount_cents':amount,'occurred_at':100,
                                   'source_attested':True,'confirm':True},t=200)

    def test_hypotheses_and_receipts_never_become_verified_revenue_or_usd_costs(self):
        with s.db() as c:
            oid=self.offer(c)
            costs=s.used(c)
            test=self.receipt(c,oid,'fixture_test_payment','test','payment',1000)
            self.receipt(c,oid,'fixture_test_refund','test','refund',300,test)
            live=self.receipt(c,oid,'fixture_live_payment','owner_declared_live','payment',2500)
            self.receipt(c,oid,'fixture_live_refund','owner_declared_live','refund',500,live)
            before=c.total_changes
            status=business.status(c,t=200)
            self.assertEqual(status['totals'],{
                'test':{'gross_cents':1000,'refunds_cents':300,'net_cents':700},
                'owner_declared_live':{'gross_cents':2500,'refunds_cents':500,'net_cents':2000}})
            self.assertEqual(status['catalog'][0]['economics']['result']['monthly_result_cents'],44000)
            self.assertFalse(status['catalog'][0]['sale_authorized'])
            self.assertEqual(status['verified_live_cents'],0)
            self.assertFalse(status['verified_live_available'])
            self.assertFalse(status['external_authorized'])
            self.assertEqual(status['currency'],'EUR')
            self.assertEqual(s.used(c),costs)
            self.assertEqual(accounting.project_total(c,self.pid),300)
            self.assertEqual(c.total_changes,before)
        self.request.assert_not_called()

    def test_invalid_refunds_do_not_change_projections(self):
        with s.db() as c:
            oid=self.offer(c)
            payment=self.receipt(c,oid,'fixture_test_payment','test','payment',1000)
            self.receipt(c,oid,'fixture_test_refund','test','refund',300,payment)
            before=c.total_changes
            with self.assertRaisesRegex(ValueError,'même mode'):
                self.receipt(c,oid,'fixture_wrong_mode','owner_declared_live','refund',100,payment)
            with self.assertRaisesRegex(ValueError,'supérieur'):
                self.receipt(c,oid,'fixture_excess_refund','test','refund',701,payment)
            with self.assertRaisesRegex(ValueError,'déjà enregistrée'):
                self.receipt(c,oid,'fixture_test_payment','test','payment',1000)
            self.assertEqual(c.total_changes,before)
            status=business.status(c,t=200)
            self.assertEqual(status['totals']['test']['net_cents'],700)
            self.assertEqual(status['totals']['owner_declared_live']['net_cents'],0)
            self.assertEqual(s.used(c),400)
        self.request.assert_not_called()


if __name__=='__main__':
    unittest.main()
