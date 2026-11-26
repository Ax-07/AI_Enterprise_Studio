"""Contracts for the action/event boundary; SQLite fixtures, no provider calls."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import moteur as m
from core import turn_execution


class TurnExecutionTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE events(id INTEGER PRIMARY KEY, mission INTEGER, task INTEGER,
                agent TEXT, action TEXT, args TEXT, result TEXT, ok INTEGER,
                created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE rewards(id INTEGER PRIMARY KEY, mission INTEGER, agent TEXT,
                event INTEGER UNIQUE, xp INTEGER, reason TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE missions(id INTEGER PRIMARY KEY, state TEXT, error TEXT,
                step INTEGER, mode TEXT);
            INSERT INTO missions VALUES(1,'en cours','',0,'demo');
            CREATE TABLE tasks(id INTEGER PRIMARY KEY, mission INTEGER, parent INTEGER,
                state TEXT, turns INTEGER, agent TEXT);
        """)
        self.s = Mock()
        self.s.db.side_effect = self.transaction
        self.cfg = {'turn_limit': 8, 'call_limit': 10}
        self.s.config.return_value = self.cfg
        self.t = {'mission': 1, 'id': 7, 'agent': 'SENTINEL'}
        self.execute = Mock(return_value={'fixture': True})

    @contextmanager
    def transaction(self):
        with self.c:
            yield self.c

    def action(self, action='calculate', target='', text='fixture', detail=''):
        return {'action': action, 'target': target, 'text': text, 'detail': detail}

    def process(self, v, mode='cloud'):
        turn_execution.process_action(self.s, 1, self.t, v, self.cfg, mode,
                                      m.action_args, m.repeat_count, self.execute,
                                      m.log, m.agent_is_auditor)

    def events(self):
        return list(self.c.execute('SELECT * FROM events ORDER BY id'))

    def rewards(self):
        return list(self.c.execute('SELECT * FROM rewards ORDER BY id'))

    def test_success_records_compact_payload_and_hash(self):
        text = 'x'*300
        v = self.action(text=text)
        self.process(v)
        self.execute.assert_called_once_with(self.s,self.t,v,self.cfg,'cloud')
        row, = self.events()
        args = json.loads(row['args'])
        self.assertEqual(args['text'],'x'*250)
        self.assertEqual(args['text_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual((row['mission'],row['task'],row['agent'],row['ok']),
                         (1,7,'SENTINEL',1))
        self.assertEqual(json.loads(row['result']),{'fixture':True})

    def test_third_identical_action_refused_before_execution_and_log(self):
        v = self.action()
        self.process(v)
        self.process(v)
        with self.assertRaisesRegex(RuntimeError,'Action identique répétée trois fois'):
            self.process(v)
        self.assertEqual(self.execute.call_count,2)
        self.assertEqual(len(self.events()),2)

    def test_same_prefix_different_text_is_not_a_repeat(self):
        for suffix in ('a','b','c'):
            self.process(self.action(text='x'*250+suffix))
        self.assertEqual(len(self.events()),3)
        self.assertEqual(self.execute.call_count,3)

    def test_expected_tool_errors_are_recorded_and_bounded(self):
        for error in (ValueError('x'*450),ArithmeticError('math'),
                      SyntaxError('syntax'),TypeError('type')):
            with self.subTest(error=type(error).__name__):
                self.execute.side_effect=error
                self.process(self.action(target=type(error).__name__))
                row=self.events()[-1]
                self.assertEqual(row['ok'],0)
                self.assertEqual(json.loads(row['result']),{'erreur':str(error)[:400]})
                # Isolate each error from the independent consecutive-failure policy.
                self.execute.side_effect=None
                self.process(self.action(target='success-'+type(error).__name__))

    def test_third_consecutive_failure_commits_before_raising(self):
        self.execute.side_effect=ValueError('fixture')
        for target in ('one','two'):
            self.process(self.action(target=target))
        with self.assertRaisesRegex(RuntimeError,'Trois outils refusés/échoués de suite'):
            self.process(self.action(target='three'))
        self.assertFalse(self.c.in_transaction)
        self.assertEqual([r['ok'] for r in self.events()],[0,0,0])

    def test_unexpected_error_propagates_without_event(self):
        self.execute.side_effect=RuntimeError('fixture unexpected')
        with self.assertRaisesRegex(RuntimeError,'fixture unexpected'):
            self.process(self.action())
        self.assertEqual(self.events(),[])

    def test_auditor_reward_once_per_filename(self):
        self.execute.return_value={'valide':True,'nom':'fixture.json','reference':False}
        self.process(self.action('check_file',target='fixture.json'))
        self.process(self.action('check_file',target='fixture.json',detail='second'))
        row,=self.rewards()
        self.assertEqual((row['mission'],row['agent'],row['xp']),
                         (1,'SENTINEL',10))
        self.assertEqual(row['event'],self.events()[0]['id'])
        self.assertEqual(len(self.events()),2)

    def test_no_reward_for_demo_reference_invalid_or_other_agent(self):
        cases=[
            ('demo','SENTINEL',{'valide':True,'nom':'demo.json'}),
            ('cloud','SENTINEL',{'valide':True,'nom':'ref.json','reference':True}),
            ('cloud','SENTINEL',{'valide':False,'nom':'invalid.json'}),
            ('cloud','SENTINEL',{'valide':True,'nom':'fixture.html'}),
            ('cloud','NEXUS',{'valide':True,'nom':'other.json'}),
        ]
        for mode,agent,result in cases:
            self.t['agent']=agent
            self.execute.return_value=result
            self.process(self.action('check_file',target=result['nom']),mode)
        self.assertEqual(self.rewards(),[])
        self.assertEqual(len(self.events()),len(cases))

    def test_legacy_run_blocks_after_three_logged_failures(self):
        with self.c:
            self.c.execute("INSERT INTO tasks VALUES(7,1,NULL,'prête',0,'SENTINEL')")
        actions=[self.action(target=x) for x in ('one','two','three')]
        with patch.object(m,'demo_action',side_effect=actions), \
             patch.object(m,'execute',side_effect=ValueError('fixture')) as execute:
            m.run(self.s,1)
            self.assertEqual(execute.call_count,3)
        row=self.c.execute('SELECT state,error FROM missions WHERE id=1').fetchone()
        self.assertEqual(row['state'],'bloquée')
        self.assertIn('Trois outils refusés/échoués de suite',row['error'])
        self.assertEqual([r['ok'] for r in self.events()],[0,0,0])
        self.assertEqual(self.c.execute('SELECT turns FROM tasks WHERE id=7').fetchone()[0],3)
        self.s.call_model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
