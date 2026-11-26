import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import serveur as s
from infrastructure.configuration import load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / 'config.json'
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write(self, **values):
        self.file.write_text(json.dumps(values), encoding='utf-8-sig')

    def load(self):
        return load_config(self.root, s.DEFAULT, s.PRICES)

    def test_defaults_and_absent_file(self):
        self.assertEqual(self.load(), {
            'html_sandbox_enabled': False, 'mission_budget': 750000,
            'call_limit': 24, 'task_limit': 8, 'turn_limit': 10,
            'mission_search_limit': 6, 'page_limit': 8, 'key': '', 'brave': '',
            'budget': 2000000, 'limit': 10, 'models': dict(s.DEFAULT)})
        self.assertFalse(self.file.exists())

    def test_overrides_and_environment_precedence(self):
        self.write(openai_budget_usd=4, mission_budget_usd=.5, brave_max_searches=3,
                   models={'ATLAS': 'gpt-6-luna'}, openai_api_key='fixture-file',
                   brave_api_key='fixture-brave', html_sandbox_enabled=True)
        before = self.file.read_bytes()
        result = self.load()
        self.assertEqual(result['budget'], 4000000)
        self.assertEqual(result['mission_budget'], 500000)
        self.assertEqual(result['limit'], 3)
        self.assertEqual(result['models']['ATLAS'], 'gpt-6-luna')
        self.assertEqual(result['models']['ORION'], s.DEFAULT['ORION'])
        self.assertEqual(result['key'], 'fixture-file')
        self.assertEqual(result['brave'], 'fixture-brave')
        self.assertTrue(result['html_sandbox_enabled'])
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-env',
                                     'BRAVE_API_KEY': 'fixture-env-brave'}):
            self.assertEqual(self.load()['key'], 'fixture-env')
            self.assertEqual(self.load()['brave'], 'fixture-env-brave')
        with patch.dict(os.environ, {'OPENAI_API_KEY': '', 'BRAVE_API_KEY': ''}):
            self.assertEqual(self.load()['key'], 'fixture-file')
            self.assertEqual(self.load()['brave'], 'fixture-brave')
        self.assertEqual(before, self.file.read_bytes())

    def test_boundaries(self):
        self.write(openai_budget_usd=0, mission_budget_usd=15, brave_max_searches=1000,
                   mission_max_calls=100, mission_max_tasks=30, task_max_turns=30,
                   mission_max_searches=50, mission_max_pages=50)
        result = self.load()
        self.assertEqual((result['budget'], result['mission_budget'], result['limit']),
                         (0, 15000000, 1000))
        self.assertEqual([result[k] for k in ('call_limit','task_limit','turn_limit',
                                             'mission_search_limit','page_limit')],
                         [100, 30, 30, 50, 50])

    def test_invalid_values_preserve_guards(self):
        cases = [
            ({'openai_budget_usd': float('nan')}, 'Budget invalide'),
            ({'openai_budget_usd': 16}, 'Budget invalide'),
            ({'brave_max_searches': 1001}, 'Budget invalide'),
            ({'mission_budget_usd': 0}, 'Budget mission invalide'),
            ({'mission_max_calls': 15}, 'mission_max_calls'),
            ({'mission_max_tasks': 31}, 'mission_max_tasks'),
            ({'task_max_turns': 4}, 'task_max_turns'),
            ({'mission_max_searches': -1}, 'mission_max_searches'),
            ({'mission_max_pages': 51}, 'mission_max_pages'),
            ({'html_sandbox_enabled': 1}, 'html_sandbox_enabled'),
            ({'models': {'ATLAS': 'unknown'}}, 'Modèle non autorisé'),
        ]
        for values, message in cases:
            with self.subTest(values=values):
                self.write(**values)
                with self.assertRaisesRegex(ValueError, message):
                    self.load()

    def test_facade_resolves_root_defaults_and_prices_at_call_time(self):
        defaults = {'ATLAS': 'fixture-model'}
        prices = {'fixture-model': (1, 2)}
        with patch.object(s, 'ROOT', self.root), patch.object(s, 'DEFAULT', defaults), \
                patch.object(s, 'PRICES', prices):
            self.assertEqual(s.config()['models'], defaults)
            self.write(models={'ATLAS': 'unknown'})
            with self.assertRaisesRegex(ValueError, 'Modèle non autorisé'):
                s.config()


if __name__ == '__main__':
    unittest.main()
