"""Mission orchestration contracts using SQLite memory and no real AI."""
from contextlib import contextmanager
import sqlite3
import unittest
from unittest.mock import Mock, patch

import moteur as m
from core import orchestration as o


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE missions(id INTEGER PRIMARY KEY, state TEXT, error TEXT, step INTEGER, mode TEXT);
            INSERT INTO missions VALUES(1,'en cours','',0,'demo');
            CREATE TABLE tasks(id INTEGER PRIMARY KEY, mission INTEGER, parent INTEGER,
                state TEXT, turns INTEGER, agent TEXT);
            CREATE TABLE events(id INTEGER PRIMARY KEY, mission INTEGER);
        """)
        self.s = Mock()
        self.s.db.side_effect = self.transaction
        self.cfg = {'turn_limit': 5, 'call_limit': 8}
        self.s.config.return_value = self.cfg

    @contextmanager
    def transaction(self):
        with self.c:
            yield self.c

    def task(self, ident, state='prête', parent=None, turns=0, mission=1, agent='ORION'):
        with self.c:
            self.c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)',
                           (ident,mission,parent,state,turns,agent))

    def status(self):
        return tuple(self.c.execute('SELECT state,error,step FROM missions WHERE id=1').fetchone())

    def test_children_before_root_and_id_order(self):
        self.task(1,agent='ATLAS')
        self.task(2,parent=1)
        self.task(3,parent=1)
        self.task(4,mission=2,parent=1,state='terminée')
        self.assertEqual(o.select_task(self.s,1,self.cfg)['id'],2)
        self.assertEqual(self.status()[2],2)
        with self.c:
            self.c.execute("UPDATE tasks SET state='terminée' WHERE id=2")
        self.assertEqual(o.select_task(self.s,1,self.cfg)['id'],3)
        with self.c:
            self.c.execute("UPDATE tasks SET state='terminée' WHERE id=3")
        self.assertEqual(o.select_task(self.s,1,self.cfg)['id'],1)

    def test_waiting_child_pauses_parent(self):
        self.task(1,agent='ATLAS')
        self.task(2,state='en attente',parent=1)
        self.assertIsNone(o.select_task(self.s,1,self.cfg))
        self.assertEqual(self.status(),('en attente','Décision du propriétaire requise.',0))

    def test_failed_child_blocks_parent(self):
        self.task(1,agent='ATLAS')
        self.task(2,state='bloquée',parent=1)
        self.assertIsNone(o.select_task(self.s,1,self.cfg))
        self.assertEqual(self.status(),('bloquée','Tâches non résolues.',0))

    def test_completed_and_empty_mission_states(self):
        self.task(1,state='terminée')
        self.assertIsNone(o.select_task(self.s,1,self.cfg))
        self.assertEqual(self.status(),('terminée','',0))
        with self.c:
            self.c.execute('DELETE FROM tasks')
            self.c.execute("UPDATE missions SET state='en cours' WHERE id=1")
        self.assertIsNone(o.select_task(self.s,1,self.cfg))
        self.assertEqual(self.status(),('bloquée','Tâches non résolues.',0))

    def test_stopped_mission_is_not_modified(self):
        self.task(1)
        with self.c:
            self.c.execute("UPDATE missions SET state='arrêtée',error='owner' WHERE id=1")
        self.assertIsNone(o.select_task(self.s,1,self.cfg))
        self.assertFalse(o.count_turn_if_running(self.s,1,{'id':1}))
        o.mark_blocked_if_running(self.s,1,RuntimeError('fixture'))
        self.assertEqual(self.status(),('arrêtée','owner',0))
        self.assertEqual(self.c.execute('SELECT turns FROM tasks WHERE id=1').fetchone()[0],0)

    def test_turn_limit_precedes_action_limit(self):
        self.task(1,turns=5)
        self.cfg['call_limit']=0
        with self.assertRaisesRegex(RuntimeError,'Plafond de tours atteint pour la tâche #1'):
            o.select_task(self.s,1,self.cfg)
        self.assertEqual(self.status(),('en cours','',0))
        with self.c:
            self.c.execute('UPDATE tasks SET turns=0 WHERE id=1')
        with self.assertRaisesRegex(RuntimeError,'Plafond d’actions de mission atteint'):
            o.select_task(self.s,1,self.cfg)
        self.assertEqual(self.status(),('en cours','',0))

    def test_action_limit_is_mission_scoped(self):
        self.task(1)
        self.cfg['call_limit']=1
        with self.c:
            self.c.execute('INSERT INTO events(mission) VALUES(2)')
        self.assertEqual(o.select_task(self.s,1,self.cfg)['id'],1)
        with self.c:
            self.c.execute('INSERT INTO events(mission) VALUES(1)')
        with self.assertRaisesRegex(RuntimeError,'Plafond d’actions de mission atteint'):
            o.select_task(self.s,1,self.cfg)

    def test_turn_counter_and_blocked_error_bounds(self):
        self.task(1)
        self.assertTrue(o.count_turn_if_running(self.s,1,{'id':1}))
        self.assertEqual(self.c.execute('SELECT turns FROM tasks WHERE id=1').fetchone()[0],1)
        o.mark_blocked_if_running(self.s,1,RuntimeError('x'*600))
        self.assertEqual(self.status(),('bloquée','x'*500,0))

    def test_run_refuses_exhausted_task_before_execution(self):
        self.task(1,turns=5)
        with patch.object(m,'demo_action') as demo, patch.object(m,'execute') as execute:
            m.run(self.s,1)
            demo.assert_not_called()
            execute.assert_not_called()
        self.s.call_model.assert_not_called()
        self.assertEqual(self.status(),('bloquée','Plafond de tours atteint pour la tâche #1',0))

    def test_run_does_not_execute_action_after_owner_stop(self):
        self.task(1)
        def stop(s,t):
            with self.c:
                self.c.execute("UPDATE missions SET state='arrêtée' WHERE id=1")
            return {'action':'finish','target':'','text':'fixture','detail':''}
        with patch.object(m,'demo_action',side_effect=stop), patch.object(m,'execute') as execute:
            m.run(self.s,1)
            execute.assert_not_called()
        self.assertEqual(self.status(),('arrêtée','',1))
        self.assertEqual(self.c.execute('SELECT turns FROM tasks WHERE id=1').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
