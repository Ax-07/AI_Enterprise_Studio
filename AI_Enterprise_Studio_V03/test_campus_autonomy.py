"""Integrated O04 contract on an isolated real schema; no paid or external calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import moteur
import campus_tools

class CampusAutonomyTests(unittest.TestCase):
    def test_simulation_and_blocked_cloud_are_distinct(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            s.init()
            cfg={**s.config(),'key':'','brave':'','budget':4000000}
            with patch.object(s,'config',return_value=cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(moteur,'fetch_page',side_effect=AssertionError('Network forbidden')) as fetch:
                with s.db() as c:demo=moteur.create(s,c,'Simulation intégrée','demo')
                s.run(demo)
                with s.db() as c:
                    cloud=moteur.create(s,c,'Cloud sans fournisseur','cloud')
                    self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(demo,)).fetchone()[0],'terminée')
                s.run(cloud)
                with s.db() as c:
                    self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(cloud,)).fetchone()[0],'bloquée')
                    self.assertEqual(s.used(c),0)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM rewards').fetchone()[0],0)
                before=s.DB.read_bytes()
                workforce=campus_tools.read(s.DB,'workforce',{},roles=moteur.ROLES,permissions=moteur.PERMS)
                summary=workforce['rows'][0]
                self.assertEqual(summary['configured'],8)
                self.assertEqual(summary['delegation_count'],4)
                self.assertEqual(summary['unresolved'],1)
                agents={r['id']:r for r in workforce['rows'] if r['kind']=='agent'}
                self.assertEqual(agents['ATLAS']['load'],[{'mode':'cloud','category':'blocked','count':1}])
                self.assertEqual(sum(x['count'] for r in agents.values() for x in r['completed_tasks'] if x['mode']=='demo'),5)
                self.assertTrue(all(x['mode']=='demo' for r in agents.values() for x in r['tool_evidence']))
                self.assertTrue(all(r['competence_rating'] is None for r in agents.values()))
                self.assertEqual({r['mode'] for r in workforce['rows'] if r['kind']=='delegation'},{'demo'})
                incidents=campus_tools.read(s.DB,'incidents',{})['rows']
                self.assertEqual(len(incidents),2)
                self.assertEqual(incidents[1]['id'],cloud)
                self.assertEqual(incidents[1]['category'],'configuration')
                self.assertFalse(incidents[1]['automatic_retry_authorized'])
                improvements=campus_tools.read(s.DB,'improvements',{})['rows']
                self.assertEqual(len(improvements),1)
                self.assertEqual(improvements[0]['counts'],[])
                self.assertFalse(improvements[0]['training_performed'])
                self.assertEqual(s.DB.read_bytes(),before)
                network.assert_not_called()
                fetch.assert_not_called()
