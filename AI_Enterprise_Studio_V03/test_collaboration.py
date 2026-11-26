"""Coordination contracts via the guarded legacy facade; no network or AI."""
from contextlib import contextmanager
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import autopilot
import commercial
import moteur as m
import periodic
import working_memory


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE missions(id INTEGER PRIMARY KEY, state TEXT);
            INSERT INTO missions VALUES(1,'en cours');
            CREATE TABLE tasks(id INTEGER PRIMARY KEY, mission INTEGER, agent TEXT,
                goal TEXT, criteria TEXT, state TEXT DEFAULT 'prête', parent INTEGER,
                turns INTEGER DEFAULT 0, result TEXT DEFAULT '');
            INSERT INTO tasks(id,mission,agent,goal,criteria)
                VALUES(7,1,'ATLAS','fixture',''),(8,1,'ORION','research','');
            CREATE TABLE requests(id INTEGER PRIMARY KEY, mission INTEGER, body TEXT, task INTEGER);
            CREATE TABLE reports(id INTEGER PRIMARY KEY, mission INTEGER, step INTEGER,
                agent TEXT, report TEXT, sources TEXT);
            CREATE TABLE searches(mission INTEGER);
        """)
        self.s = Mock()
        self.s.db.side_effect = self.transaction
        self.cfg = {'task_limit': 8, 'turn_limit': 6}
        self.period = self.start_patch(periodic, 'guard_mission')
        self.campaign = self.start_patch(autopilot, 'guard')
        self.followup = self.start_patch(commercial, 'followup_mission')
        self.followup.return_value = None

    @contextmanager
    def transaction(self):
        with self.c:
            yield self.c

    def start_patch(self, module, name):
        p = patch.object(module, name)
        self.addCleanup(p.stop)
        return p.start()

    def execute(self, action, agent='ATLAS', target='', text='', detail='', mode='cloud', turns=0):
        t = {'mission': 1, 'id': 7 if agent == 'ATLAS' else 8,
             'agent': agent, 'turns': turns}
        v = {'action': action, 'target': target, 'text': text, 'detail': detail}
        return m.execute(self.s, t, v, self.cfg, mode)

    def test_delegate_permission_and_campaign_before_write(self):
        with self.assertRaisesRegex(ValueError, 'Outil interdit à ORION'):
            self.execute('delegate','ORION',target='NEXUS',text='fixture')
        self.s.db.assert_not_called()
        self.campaign.side_effect = ValueError('campaign fixture')
        with self.assertRaisesRegex(ValueError, 'campaign fixture'):
            self.execute('delegate',target='NEXUS',text='fixture')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 2)

    def test_delegate_creates_child_with_bounded_criteria(self):
        result = self.execute('delegate',target=' NEXUS ',text='build',detail='x'*1600)
        row = self.c.execute('SELECT * FROM tasks WHERE id=?',(result['tache'],)).fetchone()
        self.assertEqual((row['mission'],row['agent'],row['parent'],row['goal'],row['state']),
                         (1,'NEXUS',7,'build','prête'))
        self.assertEqual(len(row['criteria']),1500)
        self.assertEqual(result['agent'],'NEXUS')

    def test_delegate_recipient_limit_duplicate_and_callback(self):
        for target in ('ATLAS','UNKNOWN'):
            with self.assertRaisesRegex(ValueError,'Destinataire invalide'):
                self.execute('delegate',target=target,text='fixture')
        self.cfg['task_limit'] = 2
        with self.assertRaisesRegex(ValueError,'Plafond de tâches atteint'):
            self.execute('delegate',target='ORION',text='research')
        self.cfg['task_limit'] = 8
        with self.assertRaisesRegex(ValueError,'Tâche identique déjà créée'):
            self.execute('delegate',target='ORION',text='research')
        with self.assertRaisesRegex(ValueError,'Tâche invalide'):
            self.execute('delegate',target='NEXUS',text='x'*2501)
        with patch.object(m,'add_task',return_value=99) as add:
            self.assertEqual(self.execute('delegate',target='NEXUS',text='build',detail='check'),
                             {'tache':99,'agent':'NEXUS'})
            add.assert_called_once_with(self.c,1,'NEXUS','build','check',7)

    def test_request_is_study_only_and_sets_waiting_state(self):
        with self.assertRaisesRegex(ValueError,'Objet, justification, coûts et risques requis'):
            self.execute('request',target='fixture',text='justification')
        result = self.execute('request',target='x'*170,text='y'*4100,detail='z'*1100)
        row = self.c.execute('SELECT * FROM requests').fetchone()
        data = json.loads(row['body'])
        self.assertEqual((row['mission'],row['task']), (1,7))
        self.assertEqual((len(data['objet']),len(data['justification']),len(data['risques'])),
                         (160,4000,1000))
        self.assertTrue(data['cout_estime'].startswith('Aucun achat autorisé. '))
        self.assertEqual(result['portée'],'étude seulement; aucun accès ni paiement accordé')
        self.assertEqual(self.c.execute('SELECT state FROM tasks WHERE id=7').fetchone()[0],
                         'en attente')

    def test_request_duplicate_and_mission_limit(self):
        self.execute('request',target='fixture',text='study',detail='cost')
        with self.assertRaisesRegex(ValueError,'Demande déjà formulée'):
            self.execute('request',target='fixture',text='study again',detail='cost')
        with self.c:
            self.c.executemany('INSERT INTO requests(mission,body,task) VALUES(1,?,8)',
                               [('other',)]*3)
        with self.assertRaisesRegex(ValueError,'Plafond de demandes atteint'):
            self.execute('request',target='different',text='study',detail='cost')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM requests').fetchone()[0],4)

    def test_finish_requires_report_and_atlas_delegation(self):
        with self.assertRaisesRegex(ValueError,'Rapport vide'):
            self.execute('finish',text=' ')
        with self.assertRaisesRegex(ValueError,'ATLAS doit déléguer au moins une tâche'):
            self.execute('finish',text='fixture')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)

    def test_finish_persists_report_sequence_and_provenance(self):
        with self.c:
            self.c.execute("INSERT INTO reports(mission,step,agent,report,sources) VALUES(1,4,'NEXUS','{}','[]')")
        text = 'x'*18001
        result = self.execute('finish','ORION',text=text)
        row = self.c.execute('SELECT * FROM tasks WHERE id=8').fetchone()
        report = self.c.execute('SELECT * FROM reports WHERE step=5').fetchone()
        self.assertEqual((row['state'],len(row['result'])),('terminée',18000))
        self.assertEqual((report['mission'],report['agent'],report['sources']),(1,'ORION','[]'))
        self.assertEqual(json.loads(report['report']),{'rapport':text,'requetes':[],'demandes':[]})
        self.assertEqual(result['statut'],'rapport déposé (non certifié)')

    def test_finish_rolls_back_task_when_report_insert_fails(self):
        self.c.executescript("""
            CREATE TRIGGER fail_report BEFORE INSERT ON reports
            BEGIN SELECT RAISE(ABORT,'fixture report failure'); END;
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError,'fixture report failure'):
            self.execute('finish','ORION',text='fixture')
        row = self.c.execute('SELECT state,result FROM tasks WHERE id=8').fetchone()
        self.assertEqual(tuple(row),('prête',''))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)

    def test_followup_atlas_requires_completed_orion(self):
        self.followup.return_value = {'fixture':True}
        self.execute('delegate',target='NEXUS',text='fixture')
        with self.assertRaisesRegex(ValueError,'Complément : déléguer ORION et attendre son rapport'):
            self.execute('finish',text='fixture')
        with self.c:
            self.c.execute("UPDATE tasks SET state='terminée' WHERE id=8")
        self.assertEqual(self.execute('finish',text='fixture')['tache'],7)

    def test_followup_orion_first_search_and_last_turn(self):
        self.followup.return_value = {'fixture':True}
        with patch.object(autopilot,'permitted',return_value=({'search','finish'},None)) as permitted, \
             patch.object(working_memory,'snapshot',return_value={'fixture':True}) as snapshot, \
             patch.object(working_memory,'policy',return_value={'search','finish'}) as policy:
            with self.assertRaisesRegex(ValueError,'Complément : première recherche autorisée obligatoire'):
                self.execute('finish','ORION',text='fixture')
            permitted.assert_called_once_with(self.c,1,'ORION',m.PERMS['ORION'])
            snapshot.assert_called_once()
            policy.assert_called_once()
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)
            self.assertEqual(self.execute('finish','ORION',text='limite',turns=5)['tache'],8)
            permitted.assert_called_once()


if __name__ == '__main__':
    unittest.main()
