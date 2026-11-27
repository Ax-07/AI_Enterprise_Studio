"""Catalogue contract tests: no external calls or business-state mutations."""
import unittest
from unittest.mock import patch

import commercial
import moteur as m
from core import tool_catalog as catalog
from test_agent_registry import BASELINE, fingerprint


class ToolCatalogueTests(unittest.TestCase):
    def test_historical_schema_and_guides(self):
        schema = catalog.build_schema(m.PERMS)
        guides = catalog.build_guides(commercial.OFFER_LIMIT)
        self.assertEqual(schema, m.SCHEMA)
        self.assertEqual(list(guides.items()), list(m.GUIDE.items()))
        self.assertEqual(fingerprint(schema), BASELINE['schema'])
        self.assertEqual(fingerprint(guides), BASELINE['guides'])

    def test_descriptive_catalogue_covers_all_actions_once(self):
        entries = catalog.describe(commercial.OFFER_LIMIT)
        self.assertEqual(len(entries), 21)
        self.assertEqual(set(entries), set(m.GUIDE))
        self.assertEqual(set(entries), set(m.SCHEMA['properties']['action']['enum']))
        for action, entry in entries.items():
            self.assertEqual(entry['id'], action)
            self.assertEqual(entry['guide'], m.GUIDE[action])
            self.assertTrue(entry['category'])

    def test_fresh_schema_and_guides(self):
        a = catalog.build_schema(m.PERMS)
        a['required'].clear()
        a['properties']['action']['enum'].clear()
        a['properties']['text']['type'] = 'fixture'
        self.assertEqual(catalog.build_schema(m.PERMS), m.SCHEMA)
        guides = catalog.build_guides(commercial.OFFER_LIMIT)
        guides.clear()
        self.assertEqual(catalog.build_guides(commercial.OFFER_LIMIT), m.GUIDE)
        entries = catalog.describe(commercial.OFFER_LIMIT)
        entries['finish']['guide'] = 'fixture'
        self.assertEqual(catalog.describe(commercial.OFFER_LIMIT)['finish']['guide'],
                         m.GUIDE['finish'])

    def test_supplied_business_limit_preserved(self):
        original = catalog.build_guides(commercial.OFFER_LIMIT)
        custom = catalog.build_guides(1234)
        self.assertIn('5 à 1234 caractères', custom['commercial_offer'])
        self.assertEqual({k for k in original if original[k] != custom[k]},
                         {'commercial_offer'})

    def test_schema_comes_from_permissions_not_catalogue(self):
        permissions = {'fixture': {'finish', 'custom_fixture'}}
        schema = catalog.build_schema(permissions)
        self.assertEqual(schema['properties']['action']['enum'],
                         ['custom_fixture', 'finish'])
        self.assertNotIn('custom_fixture', catalog.describe(commercial.OFFER_LIMIT))
        self.assertEqual(permissions, {'fixture': {'finish', 'custom_fixture'}})

    def test_guide_projection_is_sorted_and_does_not_expand_authorization(self):
        guides = {'search': 'not allowed', 'finish': 'fixture', 'memory': 'memory'}
        selected = catalog.select_guides(guides, {'memory', 'finish'})
        self.assertEqual(list(selected.items()), [('finish', 'fixture'), ('memory', 'memory')])
        self.assertEqual(catalog.select_guides(guides, set()), {})
        with self.assertRaises(KeyError):
            catalog.select_guides(guides, {'unknown'})

    def test_legacy_schema_and_final_turn_remain_substitutable(self):
        schema = catalog.build_schema({'fixture': {'memory', 'finish'}})
        with patch.object(m, 'SCHEMA', schema):
            self.assertTrue(m.validate_action({'action': 'memory', 'target': '',
                                               'text': '', 'detail': ''}))
            self.assertFalse(m.validate_action({'action': 'search', 'target': '',
                                                'text': '', 'detail': ''}))
            final = m.final_schema()
            self.assertEqual(final['properties']['action']['enum'], ['finish'])
            self.assertEqual(schema['properties']['action']['enum'], ['finish', 'memory'])


if __name__ == '__main__':
    unittest.main()
