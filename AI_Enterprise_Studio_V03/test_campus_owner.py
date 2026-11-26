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
