"""Freeze the V3.0.2 agent contract before refactoring the core."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

import moteur as m
import serveur as s
from core import agents

# SHA-256 of canonical UTF-8 JSON, extracted from the CI artifact 15152587501
# (V3.0.2 candidate for PR31). Ordered pairs preserve the legacy dictionary order.
BASELINE = {
    'identities': '46507add0c72cfabf70adee7db3d44b60718a46da7e02b24f79ce97823099cc6',
    'roles': 'dc5b8ae6e289eafe94356be61c05e3b7425a3329ec5cf1d41f006e86361b1e78',
    'defaults': 'a8a0f683f1eefafdd0aa0361c78ba701b19230440f7531b14781462988fd1573',
    'prices': '87ea7b3b6f0dac6b234c8216dfc7b8c7e44fe98c1ad34dfdf6854dd3c941d984',
    'permissions': 'b4551648720852b158c1239b7e6f78d3714314e112764841deb6aa67b9236969',
    'schema': 'c1b92821046ba2dc17d6cf502812d01f2e7bf6d4c928c27fff63d482c1d34435',
    'guides': 'd0bf3b0d61f7ca303810373b420dc0d6f6983bba309fc37619c90695f10ca77e',
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class AgentRegistryTests(unittest.TestCase):
    def test_historical_contract(self):
        values = {'identities': list(s.AGENTS.items()), 'roles': list(m.ROLES.items()),
                  'defaults': list(s.DEFAULT.items()), 'prices': list(s.PRICES.items()),
                  'permissions': [(k, sorted(v)) for k, v in m.PERMS.items()],
                  'schema': m.SCHEMA, 'guides': m.GUIDE}
        for key, value in values.items():
            with self.subTest(key=key):
                self.assertEqual(fingerprint(value), BASELINE[key])

    def test_profiles_and_projections_are_consistent(self):
        ids = [p.agent_id for p in agents.PROFILES]
        self.assertEqual(ids, ['ATLAS','ORION','MIDAS','NEXUS','HERMES',
                               'SENTINEL','PROMETHEUS','MNEMOS'])
        self.assertEqual(list(agents.identities().items()), list(s.AGENTS.items()))
        self.assertEqual(list(agents.roles().items()), list(m.ROLES.items()))
        self.assertEqual(list(agents.default_models().items()), list(s.DEFAULT.items()))
        self.assertEqual(set(ids), set(m.PERMS))
        self.assertTrue(all(p.default_model in s.PRICES for p in agents.PROFILES))

    def test_legacy_maps_are_independent_and_profiles_frozen(self):
        for factory in (agents.identities, agents.roles, agents.default_models):
            first, second = factory(), factory()
            first['ATLAS'] = 'fixture'
            self.assertNotEqual(first, second)
            self.assertEqual(second, factory())
        with self.assertRaises(FrozenInstanceError):
            agents.PROFILES[0].title = 'fixture'

    def test_permission_union_matches_schema_and_guide(self):
        union = set().union(*m.PERMS.values())
        self.assertEqual(len(union), 21)
        self.assertEqual(union, set(m.SCHEMA['properties']['action']['enum']))
        self.assertEqual(union, set(m.GUIDE))


if __name__ == '__main__':
    unittest.main()
