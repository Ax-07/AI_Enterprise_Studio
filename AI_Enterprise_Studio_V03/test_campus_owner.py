"""D05.1: owner projections, actual schema, no mutations or provider calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools as t

class CampusOwnerTests(unittest.TestCase):
    def test_owner_and_decisions(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network:
            s.init()
            with s.db() as c:
                mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('Mission test','cloud','en attente')").lastrowid
                task=c.execute("INSERT INTO tasks(mission,agent,goal,criteria,state) VALUES(?,'ORION','test','test','en attente')",(mid,)).lastrowid
                rid=c.execute("INSERT INTO requests(mission,task,body) VALUES(?,?,?)",(mid,task,json.dumps({'objet':'Étude','justification':'Motif','cout_estime':'inconnu','risques':'à vérifier','other':'private-extra'}))).lastrowid
                c.execute("INSERT INTO requests(mission,body,state) VALUES(?,'malformed','refusée')",(mid,))
                for i in range(12):
                    c.execute("INSERT INTO missions(title,mode,state) VALUES(?,'demo','en cours')",('Simulation '+str(i),))
                c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?,'test',1000,500,'mesuré','ORION')",(mid,))
                c.execute("INSERT INTO ledger(mission,model,reserved,state,agent) VALUES(?,'test',2000,'réservé','ORION')",(mid,))
            before=s.DB.read_bytes()
            resources={'budget':4000000,'search_limit':10,'mission_budget':750000,'mission_calls':24,'openai_configured':True,'brave_configured':False,'sandbox_enabled':False,'key':'must-not-return'}
            r=t.read(s.DB,'owner',{},roles=s.moteur.ROLES,resources=resources)['rows'][0]
            self.assertEqual(r['remaining'],3997500)
            self.assertEqual(r['measured'],500)
            self.assertEqual(r['unmeasured'],2000)
            self.assertEqual(r['pending'],1)
            self.assertEqual(r['configured_agents'],8)
            self.assertEqual(r['active_counts']['missions'],12)
            self.assertEqual(len(r['active']['missions']),10)
            self.assertEqual(r['attention_count'],1)
            self.assertEqual(r['attention'][0]['id'],mid)
            self.assertEqual(r['pending_decisions'][0]['id'],rid)
            self.assertTrue(r['pending_decisions'][0]['may_resume'])
            self.assertIn({'mode':'demo','state':'en cours','count':12},r['mission_counts'])
            self.assertNotIn('private-extra',json.dumps(r))
            self.assertNotIn('must-not-return',json.dumps(r))
            decisions=t.read(s.DB,'decisions',{})['rows']
            self.assertEqual(decisions[0]['id'],rid)
            self.assertTrue(decisions[0]['may_resume'])
            self.assertEqual(decisions[0]['objet'],'Étude')
            self.assertNotIn('private-extra',json.dumps(decisions))
            self.assertIsNone(decisions[1]['objet'])
            self.assertEqual(s.DB.read_bytes(),before)
            network.assert_not_called()

    def test_nested_authorization_commitments(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network:
            s.init()
            with s.db() as c:
                mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('Fixture','cloud','terminée')").lastrowid
                cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('Fixture',100000,1,'{}',3,'interrompu')").lastrowid
                c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'commercial')",(cid,mid))
                pid=c.execute("INSERT INTO enterprise_plans(budget,per_campaign,max_campaigns,search_cap,explore,state) VALUES(200000,100000,2,5,0,'paused')").lastrowid
                c.execute("INSERT INTO enterprise_plan_queue(plan,kind,reason,campaign) VALUES(?,'commercial','fixture',?)",(pid,cid))
                gid=c.execute("""INSERT INTO periodic_grants(cadence,seconds,periods,starts,expires,last_seen,total_budget,period_budget,per_campaign,max_campaigns,total_search,period_search,explore,state)
                    VALUES('daily',86400,2,1000,173800,1000,400000,200000,100000,2,10,5,0,'active')""").lastrowid
                c.execute("INSERT INTO periodic_slots(grant_id,slot,starts,expires,plan) VALUES(?,0,1000,87400,?)",(gid,pid))
                c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?,'fixture',10000,8000,'mesuré','ORION')",(mid,))
                c.execute("INSERT INTO ledger(mission,model,reserved,state,agent) VALUES(?,'fixture',2000,'réservé','ORION')",(mid,))
                c.execute("INSERT INTO searches(mission,query,status) VALUES(?,'private-query','ok')",(mid,))
            before=s.DB.read_bytes()
            with patch('periodic.now',return_value=2000):
                rows={r['kind']:r for r in t.read(s.DB,'home',{})['rows']}
            for r in rows.values():
                self.assertEqual(r['committed'],10000)
                self.assertEqual(r['searches'],1)
            self.assertEqual(rows['campaign']['remaining'],90000)
            self.assertEqual(rows['campaign']['plan_id'],pid)
            self.assertEqual(rows['campaign']['grant_id'],gid)
            self.assertEqual(rows['plan']['remaining'],190000)
            self.assertEqual(rows['plan']['grant_id'],gid)
            self.assertEqual(rows['periodic']['remaining'],390000)
            self.assertEqual(rows['periodic']['search_remaining'],9)
            self.assertTrue(rows['periodic']['within_grant_window'])
            self.assertEqual(rows['periodic']['slot_details'][0]['plan'],pid)
            self.assertNotIn('private-query',json.dumps(rows))
            with patch('periodic.now',return_value=173800):
                g=next(r for r in t.read(s.DB,'home',{})['rows'] if r['kind']=='periodic')
                self.assertFalse(g['within_grant_window'])
                self.assertEqual(g['state'],'active')
            self.assertEqual(s.DB.read_bytes(),before)
            network.assert_not_called()
