"""Regression contracts for internal actions through the guarded legacy facade."""
from contextlib import contextmanager
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import autopilot
import commercial
import intelligence
import moteur as m
import periodic


class InternalExecutionTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE missions(id INTEGER PRIMARY KEY, state TEXT, mode TEXT);
            INSERT INTO missions VALUES(1,'en cours','cloud'),(2,'terminée','cloud');
            CREATE TABLE opportunities(id INTEGER PRIMARY KEY, mission INTEGER, title TEXT,
                body TEXT, next_test TEXT, UNIQUE(mission,title));
            CREATE TABLE artifacts(id INTEGER PRIMARY KEY, mission INTEGER, name TEXT,
                version INTEGER, agent TEXT, content TEXT, description TEXT);
            CREATE TABLE mission_artifact_refs(mission INTEGER, artifact INTEGER);
            CREATE TABLE reports(id INTEGER PRIMARY KEY, mission INTEGER, agent TEXT,
                report TEXT, sources TEXT);
            CREATE TABLE requests(id INTEGER PRIMARY KEY, mission INTEGER, body TEXT);
            CREATE TABLE tasks(id INTEGER PRIMARY KEY, mission INTEGER, result TEXT);
        """)
        self.s = Mock()
        self.s.db.side_effect = self.transaction
        self.period = self.start_patch(periodic, 'guard_mission')
        self.campaign = self.start_patch(autopilot, 'guard')

    @contextmanager
    def transaction(self):
        with self.c:
            yield self.c

    def start_patch(self, module, name):
        p = patch.object(module, name)
        self.addCleanup(p.stop)
        return p.start()

    def execute(self, action, agent, target='', text='', detail='', mode='cloud'):
        t = {'mission': 1, 'id': 7, 'agent': agent}
        v = {'action': action, 'target': target, 'text': text, 'detail': detail}
        return m.execute(self.s, t, v, {}, mode)

    def test_calculation_uses_current_legacy_callback(self):
        with patch.object(m, 'calc', return_value=42) as calc:
            result = self.execute('calculate', 'MIDAS', text='6*7')
            calc.assert_called_once_with('6*7')
        self.assertEqual(result, {'expression': '6*7', 'resultat': 42,
                         'note': 'Exactitude arithmétique seulement; hypothèses non validées.'})

    def test_stopped_mission_refuses_before_action(self):
        with self.c:
            self.c.execute("UPDATE missions SET state='arrêtée' WHERE id=1")
        with patch.object(m, 'calc') as calc:
            with self.assertRaisesRegex(ValueError, 'Mission arrêtée'):
                self.execute('calculate', 'MIDAS', text='1+1')
            calc.assert_not_called()

    def test_opportunity_upsert_and_bounds(self):
        with self.assertRaisesRegex(ValueError, 'Opportunité invalide'):
            self.execute('opportunity', 'ORION', target='x'*161, text='fixture')
        first = self.execute('opportunity', 'ORION', target=' fixture ',
                             text='a'*8100, detail='b'*2100)
        row = self.c.execute('SELECT * FROM opportunities').fetchone()
        self.assertEqual((len(row['body']), len(row['next_test'])), (8000, 2000))
        self.assertEqual(first['statut'], 'hypothèse')
        second = self.execute('opportunity', 'ORION', target='fixture', text='updated')
        self.assertEqual(first['opportunity'], second['opportunity'])
        self.assertEqual(self.c.execute('SELECT body FROM opportunities').fetchone()[0],
                         'updated')

    def test_commercial_and_economic_modes_and_callbacks(self):
        with patch.object(commercial, 'execute', return_value={'commercial': True}) as ce, \
             patch.object(intelligence, 'assess', return_value={'assessment': True}) as ae:
            with self.assertRaisesRegex(ValueError, 'Préparation commerciale Cloud uniquement'):
                self.execute('commercial_offer', 'HERMES', mode='demo')
            with self.assertRaisesRegex(ValueError, 'Évaluation Cloud, detail vide requis'):
                self.execute('assess_opportunity', 'MIDAS', detail='invalid')
            ce.assert_not_called()
            ae.assert_not_called()
            self.assertEqual(self.execute('commercial_offer', 'HERMES', text='{}'),
                             {'commercial': True})
            ce.assert_called_once_with(self.c, {'mission': 1, 'id': 7, 'agent': 'HERMES'},
                                       'commercial_offer', '', '{}', '')
            self.assertEqual(self.execute('assess_opportunity', 'MIDAS', target='1', text='{}'),
                             {'assessment': True})
            ae.assert_called_once_with(self.c, 1, 'MIDAS', '1', '{}')

    def test_file_versions_and_idempotence(self):
        with self.assertRaisesRegex(ValueError, 'Nom ou contenu invalide'):
            self.execute('write_file', 'NEXUS', target='../fixture.json', text='{}')
        one = self.execute('write_file', 'NEXUS', target='fixture.json', text='{}')
        same = self.execute('write_file', 'NEXUS', target='fixture.json', text='{}')
        two = self.execute('write_file', 'NEXUS', target='fixture.json', text='{"a":1}')
        self.assertEqual((one['version'], same['version'], two['version']), (1,1,2))
        self.assertTrue(same['identique'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 2)
        self.assertEqual(self.execute('read_file','SENTINEL',target='fixture.json')['contenu'],
                         '{"a":1}')
        self.assertTrue(self.execute('check_file','SENTINEL',target='fixture.json')['valide'])

    def test_file_limit_and_rollback_on_callback_failure(self):
        with patch.object(m, 'check', side_effect=RuntimeError('fixture')):
            with self.assertRaisesRegex(RuntimeError, 'fixture'):
                self.execute('write_file', 'NEXUS', target='fixture.json', text='{}')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 0)
        with self.c:
            self.c.executemany('INSERT INTO artifacts(mission,name,version) VALUES(1,?,1)',
                               [(str(i)+'.json',) for i in range(25)])
        with self.assertRaisesRegex(ValueError, 'Plafond de versions atteint'):
            self.execute('write_file', 'NEXUS', target='fixture.json', text='{}')

    def test_reference_scoping_and_file_listing(self):
        with self.c:
            self.c.execute("INSERT INTO artifacts VALUES(8,2,'reference.json',1,'NEXUS','{}','fixture')")
        with self.assertRaisesRegex(ValueError, 'Référence non autorisée'):
            self.execute('read_file','SENTINEL',target='ref:8')
        with self.c:
            self.c.execute('INSERT INTO mission_artifact_refs VALUES(1,8)')
        files = self.execute('list_files','SENTINEL')
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0]['lecture_seule'])
        self.assertEqual(files[0]['target'], 'ref:8')
        result = self.execute('read_file','SENTINEL',target='ref:8')
        self.assertEqual(result['mission_source'], 2)
        self.assertTrue(result['reference'])
        with self.assertRaisesRegex(ValueError, 'Référence non autorisée'):
            self.execute('read_file','SENTINEL',target='ref:9')

    def test_memory_and_report_provenance(self):
        with self.c:
            self.c.execute("INSERT INTO opportunities VALUES(3,2,'fixture','fixture body','next')")
            self.c.execute("INSERT INTO reports VALUES(5,2,'ORION',?,?)",
                           (json.dumps({'rapport':'fixture'}), '[]'))
        exact = self.execute('memory','MNEMOS',target='opportunity:3')['résultats'][0]
        self.assertEqual((exact['id'], exact['mission'], exact['mode']), (3,2,'cloud'))
        with self.assertRaisesRegex(ValueError, 'Mémoire exacte'):
            self.execute('memory','MNEMOS',target='opportunity:3',text='invalid')
        lexical = self.execute('memory','MNEMOS',text='fixture')['résultats']
        self.assertEqual({(r['type'],r['id']) for r in lexical},
                         {('opportunities',3),('reports',5)})
        result = self.execute('read_report','MNEMOS',target='5')
        self.assertEqual(result['rapport_non_certifié'], {'rapport':'fixture'})
        self.assertEqual(result['mission'], 2)
        with self.assertRaisesRegex(ValueError, 'Rapport absent'):
            self.execute('read_report','MNEMOS',target='6')


if __name__ == '__main__':
    unittest.main()
