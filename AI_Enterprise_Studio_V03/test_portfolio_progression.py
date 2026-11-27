"""Portfolio progression contracts using real local history and explicit test doubles."""
import hashlib
import json
import unittest
from unittest.mock import patch

import autopilot as a
import portfolio as p
import serveur as s
import test_portfolio as tp
from departments import portfolio_progression as pp


class PortfolioProgressionTests(unittest.TestCase):
    setUp=tp.PortfolioTests.setUp
    historical=tp.PortfolioTests.historical
    start=tp.PortfolioTests.start

    def flags(self,**changes):
        return {**dict.fromkeys(a.FLAGS,True),**changes}

    def test_create_and_economic_hold_precedes_production(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            step,reason=p.next_step(c,new,self.flags())
            self.assertEqual(step[0:2],('create',None))
            self.assertEqual(step[2]['id'],opp)
            self.assertIsNone(p.next_step(c,new,self.flags(production=False))[0])
            with patch.object(p,'economic_hold',return_value=True) as hold:
                step,reason=p.next_step(c,new,self.flags())
                self.assertIsNone(step)
                self.assertIn('Production suspendue',reason)
                hold.assert_called_once_with(c,opp)
            with patch.object(p,'history',return_value=[{'id':1}]):
                self.assertIsNone(p.next_step(c,new,self.flags())[0])

    def test_laboratory_gate_and_test_permission(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            c.execute("UPDATE artifacts SET name='audit_catalogue.html' WHERE id=?",(fixed,))
            for proof in (None,{'status':'unavailable'}):
                with patch.object(p.laboratory,'canonical',return_value=proof):
                    self.assertEqual(p.next_step(c,old,self.flags())[0],('laboratory',fixed,None))
                    self.assertIsNone(p.next_step(c,old,self.flags(tests=False))[0])
            with patch.object(p.laboratory,'canonical',return_value={'status':'failed'}):
                self.assertIsNone(p.next_step(c,old,self.flags())[0])
            with patch.object(p.laboratory,'canonical',return_value={'status':'passed'}):
                self.assertEqual(p.next_step(c,old,self.flags())[0],('market',fixed,None))

    def test_exact_proof_and_failure_priority(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(fixed,))
            self.assertEqual(p.next_step(c,old,self.flags())[0],('functional',fixed,None))
            self.assertIsNone(p.next_step(c,old,self.flags(tests=False))[0])
            mid=c.execute('SELECT mission FROM artifacts WHERE id=?',(fixed,)).fetchone()[0]
            for status in ('passed','failed'):
                result={'status':status,'sha256':hashlib.sha256(b'changed').hexdigest(),
                        'checks':[{'name':'fixture','passed':status=='passed'}]}
                c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL','{}',?)",
                          (fixed,mid,json.dumps(result)))
            self.assertEqual(p.next_step(c,old,self.flags())[0],('improve',fixed,None))
            self.assertIsNone(p.next_step(c,old,self.flags(production=False))[0])
            with patch.object(p,'history',return_value=[{'id':mid}]):
                self.assertIsNone(p.next_step(c,old,self.flags())[0])

    def test_market_permission_and_prior_attempt(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            self.assertEqual(p.next_step(c,old,self.flags())[0],('market',fixed,None))
            self.assertIsNone(p.next_step(c,old,self.flags(market=False))[0])
            with patch.object(p,'history',return_value=[{'id':1}]) as history:
                self.assertIsNone(p.next_step(c,old,self.flags())[0])
                history.assert_called_once_with(c,old,'market',fixed)

    def test_priority_least_recent_then_id_and_read_only(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            first=p.recommend(c,self.flags())
            self.assertEqual(first['id'],old)
            ids=[]
            for origin in ('fixture:tie1','fixture:tie2'):
                ids.append(c.execute('INSERT INTO projects(origin,title) VALUES(?,?)',(origin,origin)).lastrowid)
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                with patch.object(p,'next_step',return_value=(('create',None,{}),'fixture')):
                    self.assertEqual(p.recommend(c,self.flags()),{'id':min(ids),'kind':'create','reason':'fixture'})
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')
            p.set_state(c,old,'paused')
            self.assertEqual(p.recommend(c,self.flags())['id'],new)

    def test_selection_permissions_and_no_work_fallback(self):
        *_,fixed,opp,old,new=self.historical()
        with s.db() as c:
            self.assertEqual(p.select(c,'auto',self.flags()),(old,'project'))
            self.assertEqual(p.select(c,new,self.flags()),(new,'project'))
            self.assertEqual(p.select(c,'explore',self.flags()),(None,'explore'))
            for value in (True,0,-1,1.0,'1',9007199254740992):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Activité invalide'):
                    p.select(c,value,self.flags())
            for pid in (old,new):p.set_state(c,pid,'archived')
            self.assertIsNone(p.recommend(c,self.flags()))
            self.assertEqual(p.select(c,'auto',self.flags()),(None,'explore'))
            with self.assertRaisesRegex(ValueError,'Exploration non autorisée'):
                p.select(c,'explore',self.flags(research=False))
            with self.assertRaisesRegex(ValueError,'Aucune activité'):
                p.select(c,'auto',self.flags(research=False))
            with self.assertRaisesRegex(ValueError,'Activité inactive ou inconnue'):
                p.select(c,old,self.flags())

    def test_live_legacy_callbacks_and_state_guard_preserved(self):
        *_,fixed,opp,old,new=self.historical()
        flags=self.flags()
        with s.db() as c:
            with patch.object(pp,'next_step',return_value=(None,'fixture')) as step:
                self.assertEqual(p.next_step(c,old,flags),(None,'fixture'))
                step.assert_called_once_with(c,old,flags,project=p.project,latest=p.latest,
                    economic_hold=p.economic_hold,history=p.history,evidence=p.evidence,laboratory=p.laboratory)
            with patch.object(pp,'recommend',return_value=None) as rec:
                self.assertIsNone(p.recommend(c,flags))
                rec.assert_called_once_with(c,flags,next_step=p.next_step)
            with patch.object(pp,'select',return_value=(old,'project')) as select:
                self.assertEqual(p.select(c,'auto',flags),(old,'project'))
                select.assert_called_once_with(c,'auto',flags,recommend=p.recommend,project=p.project,next_step=p.next_step)
        cid=self.start(project=new)
        with s.db() as c:
            with self.assertRaisesRegex(ValueError,'Arrêter le travail actif'):
                p.set_state(c,new,'paused')
            self.assertEqual(p.project(c,new)['state'],'active')


if __name__=='__main__':
    unittest.main()
