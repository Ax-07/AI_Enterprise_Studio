"""D07: real engine schema, persisted state and actual parent-child relations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_live

class CampusActivityTests(unittest.TestCase):
    def test_activity_and_delegations(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network:
            s.init()
            with s.db() as db:
                def mission(mode,state,engine='dynamic'):
                    return db.execute('INSERT INTO missions(title,mode,state,engine) VALUES(?,?,?,?)',('test',mode,state,engine)).lastrowid
                def task(mid,agent,state,parent=None):
                    return db.execute('INSERT INTO tasks(mission,agent,goal,criteria,state,parent) VALUES(?,?,?,?,?,?)',(mid,agent,'private-goal','private-criteria',state,parent)).lastrowid
                mid=mission('cloud','en cours')
                root=task(mid,'ATLAS','prête')
                child=task(mid,'ORION','prête',root)
                db.execute('UPDATE missions SET step=? WHERE id=?',(child,mid))
                mid2=mission('demo','en cours')
                task(mid2,'NEXUS','en cours')
                mid3=mission('cloud','bloquée')
                task(mid3,'MIDAS','prête')
                mid4=mission('cloud','en attente')
                task(mid4,'HERMES','en attente')
                mid5=mission('cloud','terminée')
                task(mid5,'SENTINEL','en cours')
                mid6=mission('cloud','en cours','legacy')
                task(mid6,'MNEMOS','prête')
                task(mid5,'PROMETHEUS','terminée',root) # cross-mission parent must be ignored
            before=s.DB.read_bytes()
            data=campus_live.snapshot(s.DB,s.AGENTS,4000000,s.VERSION)
            agents={a['id']:a['activity'] for b in data['buildings'] for a in b['agents']}
            self.assertEqual(agents['ATLAS'],[{'mode':'cloud','state':'queued','count':1}])
            self.assertEqual(agents['ORION'],[{'mode':'cloud','state':'selected','count':1}])
            self.assertEqual(agents['NEXUS'],[{'mode':'demo','state':'running_recorded','count':1}])
            self.assertEqual(agents['MIDAS'][0]['state'],'blocked')
            self.assertEqual(agents['HERMES'][0]['state'],'waiting')
            self.assertEqual(agents['SENTINEL'],[])
            self.assertEqual(agents['MNEMOS'],[])
            self.assertEqual(agents['PROMETHEUS'],[])
            edges=data['activity']['delegations']
            self.assertEqual(len(edges),1)
            self.assertEqual((edges[0]['id'],edges[0]['from_agent'],edges[0]['to_agent']),(child,'ATLAS','ORION'))
            self.assertEqual(edges[0]['mode'],'cloud')
            self.assertNotIn('private-goal',str(data))
            self.assertEqual(s.DB.read_bytes(),before)
            network.assert_not_called()
