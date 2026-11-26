"""Execution boundary regression tests with SQLite fixtures and fake transports."""
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import autopilot
import connectors
import moteur as m
import periodic
import research


class ExecutionHandlerTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE missions(id INTEGER PRIMARY KEY, state TEXT);
            INSERT INTO missions VALUES(1,'en cours');
            CREATE TABLE searches(mission INTEGER, query TEXT, status TEXT, result TEXT);
            CREATE TABLE fetched(id INTEGER PRIMARY KEY, mission INTEGER, url TEXT,
                                 state TEXT, content TEXT);
            CREATE TABLE verification_results(mission INTEGER, agent TEXT);
        """)
        self.s = Mock()
        self.s.db.side_effect = lambda: self.c
        self.cfg = {'brave': 'fixture', 'limit': 4, 'mission_search_limit': 3, 'page_limit': 2}
        self.url = 'https://example.invalid/fixture'
        self.period = self.start_patch(periodic, 'guard_mission')
        self.campaign = self.start_patch(autopilot, 'guard')
        self.invoke = self.start_patch(connectors, 'invoke')
        self.fetch = self.start_patch(m, 'fetch_page')
        self.resolve = self.start_patch(m, 'resolve_artifact')
        self.spec = self.start_patch(m, 'verification_spec')
        self.record = self.start_patch(m, 'record_verification')

    def start_patch(self, module, name):
        patcher = patch.object(module, name)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def execute(self, action, agent='ORION', target='', text='', detail='', mode='cloud'):
        t = {'mission': 1, 'id': 7, 'agent': agent}
        v = {'action': action, 'target': target, 'text': text, 'detail': detail}
        return m.execute(self.s, t, v, self.cfg, mode)

    def allow_read(self):
        with self.c:
            self.c.execute("INSERT INTO searches VALUES(1,?, 'reçue',?)",
                           ('fixture', json.dumps([{'url': self.url}])))

    def test_connector_mode_detail_and_live_substitution(self):
        with self.assertRaisesRegex(ValueError, 'Connecteur Cloud, detail vide requis'):
            self.execute('connector', mode='demo')
        with self.assertRaisesRegex(ValueError, 'Connecteur Cloud, detail vide requis'):
            self.execute('connector', detail='invalid')
        self.invoke.assert_not_called()
        self.invoke.return_value = {'fixture': True}
        self.assertEqual(self.execute('connector', target='  fixture  ', text='{}'),
                         {'fixture': True})
        self.invoke.assert_called_once_with(self.s, 'fixture', '{}', 1, 7, 'ORION')

    def test_no_search_or_read_in_simulation(self):
        for action in ('search', 'read'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, 'Réseau interdit en simulation'):
                    self.execute(action, text='fixture', target=self.url, mode='demo')
        self.s.search.assert_not_called()
        self.fetch.assert_not_called()

    def test_search_key_query_cache_and_quotas(self):
        self.cfg['brave'] = ''
        with self.assertRaisesRegex(ValueError, 'Clé Brave manquante'):
            self.execute('search', text='fixture')
        self.cfg['brave'] = 'fixture'
        with self.assertRaisesRegex(ValueError, 'Requête de 1 à 200 caractères'):
            self.execute('search', text=' ')
        self.allow_read()
        self.cfg['limit'] = 1
        self.assertEqual(self.execute('search', text=' fixture '),
                         {'cache': True, 'extraits_non_vérifiés': [{'url': self.url}]})
        with self.assertRaisesRegex(ValueError, 'Plafond Brave cumulatif atteint'):
            self.execute('search', text='other')
        self.cfg['limit'] = 4
        self.cfg['mission_search_limit'] = 1
        with self.assertRaisesRegex(ValueError, 'Plafond Brave de mission atteint'):
            self.execute('search', text='other')
        self.s.search.assert_not_called()

    def test_search_success_passes_current_config(self):
        rows = [{'url': self.url}]
        self.s.search.return_value = rows
        result = self.execute('search', text=' fixture ')
        self.assertEqual(result['extraits_non_vérifiés'], rows)
        self.s.search.assert_called_once_with(1, ['fixture'], self.cfg)

    def test_read_requires_mission_source_and_quota(self):
        with self.assertRaisesRegex(ValueError, 'URL non issue des résultats Brave'):
            self.execute('read', target=self.url)
        self.allow_read()
        self.cfg['page_limit'] = 0
        with self.assertRaisesRegex(ValueError, 'Plafond de lecture atteint'):
            self.execute('read', target=self.url)
        self.fetch.assert_not_called()
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM fetched').fetchone()[0], 0)

    def test_read_reserves_before_transport_and_reuses_cache(self):
        self.allow_read()

        def reply(url):
            row = self.c.execute('SELECT * FROM fetched').fetchone()
            self.assertEqual((row['mission'], row['url'], row['state']),
                             (1, self.url, 'tentée'))
            self.assertFalse(self.c.in_transaction)
            self.assertEqual(url, self.url)
            return {'text': 'fixture'}

        self.fetch.side_effect = reply
        result = self.execute('read', target=self.url)
        self.assertEqual(result, {'text': 'fixture', 'page_ref': 1})
        self.cfg['page_limit'] = 0
        self.assertEqual(self.execute('read', target=self.url), {**result, 'cache': True})
        self.fetch.assert_called_once_with(self.url)
        self.assertEqual(self.c.execute('SELECT state FROM fetched').fetchone()[0], 'reçue')

    def test_read_failure_is_recorded_and_not_retried(self):
        self.allow_read()
        self.fetch.side_effect = TimeoutError('private-fixture')
        diagnostic = {'code': 'fixture', 'message': 'timeout', 'advice': 'other'}
        with patch.object(research, 'failure', return_value=diagnostic) as classifier:
            with self.assertRaises(ValueError) as error:
                self.execute('read', target=self.url)
            self.assertEqual(str(error.exception), 'Lecture indisponible : fixture timeout · other')
            classifier.assert_called_once()
        row = self.c.execute('SELECT state,content FROM fetched').fetchone()
        self.assertEqual(row['state'], 'échec')
        self.assertEqual(json.loads(row['content']), {'failure': diagnostic})
        with self.assertRaisesRegex(ValueError, 'Lecture déjà échouée'):
            self.execute('read', target=self.url)
        self.fetch.assert_called_once()

    def test_file_verification_mode_state_reference_and_limit(self):
        with self.assertRaisesRegex(ValueError, 'réservés aux missions Cloud'):
            self.execute('test_file', agent='NEXUS', mode='demo')
        with self.c:
            self.c.execute("UPDATE missions SET state='arrêtée'")
        with self.assertRaisesRegex(ValueError, 'Mission arrêtée'):
            self.execute('test_file', agent='NEXUS')
        self.resolve.assert_not_called()
        with self.c:
            self.c.execute("UPDATE missions SET state='en cours'")
        self.resolve.return_value = (None, False)
        with self.assertRaisesRegex(ValueError, 'Fichier absent'):
            self.execute('test_file', agent='NEXUS')
        self.resolve.return_value = ({'id': 9, 'name': 'fixture.json'}, False)
        with self.c:
            self.c.executemany("INSERT INTO verification_results VALUES(1,?)",
                               [('NEXUS',)] * 8)
        with self.assertRaisesRegex(ValueError, 'Plafond de tests de mission atteint'):
            self.execute('test_file', agent='NEXUS')
        self.spec.assert_not_called()
        self.record.assert_not_called()

    def test_file_verification_calls_current_handlers_after_transaction(self):
        row = {'id': 9, 'name': 'fixture.json'}
        self.resolve.return_value = (row, False)
        self.spec.return_value = 'fixture spec'

        def record(s, artifact, mid, agent, spec, cfg):
            self.assertFalse(self.c.in_transaction)
            self.assertEqual(artifact, row)
            self.assertIsNot(artifact, row)
            return {'verification_id': 4}

        self.record.side_effect = record
        self.assertEqual(self.execute('test_file', agent='SENTINEL',
                                      target='fixture.json', text='input'),
                         {'verification_id': 4})
        self.resolve.assert_called_once_with(self.c, 1, 'fixture.json')
        self.spec.assert_called_once_with(self.c, 1, row, 'input')
        self.record.assert_called_once_with(self.s, row, 1, 'SENTINEL',
                                            'fixture spec', self.cfg)


if __name__ == '__main__':
    unittest.main()
