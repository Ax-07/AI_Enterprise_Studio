"""Permanent permissions and authorization boundaries; no external transport."""
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch

import autopilot
import commercial
import connectors
import moteur as m
import periodic
from core import permissions as p
from test_agent_registry import BASELINE, fingerprint


class PermissionRegistryTests(unittest.TestCase):
    def build(self):
        return p.build_permissions(m.ROLES, connectors.REGISTRY[connectors.PUBLIC]['roles'],
                                   commercial.ACTIONS)

    def test_exact_historical_matrix(self):
        actual = self.build()
        self.assertEqual(actual, m.PERMS)
        self.assertEqual(list(actual), list(m.ROLES))
        self.assertEqual(len(actual), 8)
        self.assertEqual(len(set().union(*actual.values())), 21)
        self.assertEqual(sum(map(len, actual.values())), 89)
        self.assertEqual(fingerprint([(k, sorted(v)) for k, v in actual.items()]),
                         BASELINE['permissions'])
        self.assertEqual(fingerprint(m.SCHEMA), BASELINE['schema'])
        self.assertEqual(fingerprint(m.GUIDE), BASELINE['guides'])

    def test_fresh_independent_projection(self):
        first, second = self.build(), self.build()
        first['ATLAS'].add('fixture')
        first['ORION'].discard('finish')
        self.assertEqual(second, m.PERMS)
        self.assertNotIn('fixture', second['ATLAS'])
        self.assertIn('finish', second['ORION'])
        self.assertIn('finish', first['MIDAS'])

    def test_supplied_registries_are_authoritative(self):
        grants = p.build_permissions(m.ROLES, ('MNEMOS',), {'fixture': 'NEXUS'})
        self.assertEqual({a for a, actions in grants.items() if 'connector' in actions},
                         {'MNEMOS'})
        self.assertEqual({a for a, actions in grants.items() if 'fixture' in actions},
                         {'NEXUS'})
        self.assertFalse(set(commercial.ACTIONS) & set().union(*grants.values()))

    def test_unknown_roles_fail_without_widening_grants(self):
        for roles, actions in [(('UNKNOWN',), {}), ((), {'fixture': 'UNKNOWN'})]:
            with self.subTest(roles=roles, actions=actions):
                with self.assertRaises(KeyError):
                    p.build_permissions(m.ROLES, roles, actions)
        with self.assertRaises(KeyError):
            p.require_action(self.build(), 'UNKNOWN', 'finish')

    def test_every_agent_action_pair_and_unknown_action(self):
        grants = self.build()
        actions = set().union(*grants.values()) | {'unknown_action'}
        for agent, allowed in grants.items():
            for action in actions:
                with self.subTest(agent=agent, action=action):
                    if action in allowed:
                        self.assertIsNone(p.require_action(grants, agent, action))
                    else:
                        with self.assertRaises(ValueError) as error:
                            p.require_action(grants, agent, action)
                        self.assertEqual(str(error.exception), 'Outil interdit à ' + agent)

    def test_permanent_grant_is_not_operational_authorization(self):
        grants = self.build()
        self.assertIn('commercial_offer', grants['HERMES'])
        with patch.object(autopilot, 'link', return_value=None):
            allowed, campaign = autopilot.permitted(object(), 1, 'HERMES', grants['HERMES'])
        self.assertIsNone(campaign)
        self.assertNotIn('commercial_offer', allowed)
        self.assertIn('commercial_offer', grants['HERMES'])


class PermissionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.c = object()
        self.s = Mock()
        self.s.db.side_effect = lambda: nullcontext(self.c)
        self.t = {'mission': 1, 'id': 2, 'agent': 'MNEMOS'}
        self.v = {'action': 'connector', 'target': ' fixture ', 'text': '', 'detail': ''}

    def test_static_rejection_precedes_all_operational_guards(self):
        with patch.object(periodic, 'guard_mission') as period, \
             patch.object(autopilot, 'guard') as campaign, \
             patch.object(connectors, 'invoke') as invoke:
            with self.assertRaises(ValueError) as error:
                m.execute(self.s, self.t, self.v, {}, 'cloud')
            self.assertEqual(str(error.exception), 'Outil interdit à MNEMOS')
            self.s.db.assert_not_called()
            period.assert_not_called()
            campaign.assert_not_called()
            invoke.assert_not_called()

    def test_legacy_map_substitution_and_guard_order(self):
        # Explicit fixture substitution, never a production permission change.
        trace = []
        grants = {'MNEMOS': {'connector'}}

        def period(c, mid):
            trace.append('period')
            raise ValueError('period fixture')

        def campaign(c, mid, agent, action, target, base):
            trace.append('campaign')
            self.assertIs(base, grants[agent])
            self.assertEqual((c, mid, agent, action, target),
                             (self.c, 1, 'MNEMOS', 'connector', 'fixture'))
            raise ValueError('campaign fixture')

        self.v['text'] = 'x' * 24001
        with patch.object(m, 'PERMS', grants), \
             patch.object(periodic, 'guard_mission', side_effect=period) as pg, \
             patch.object(autopilot, 'guard', side_effect=campaign) as cg, \
             patch.object(connectors, 'invoke') as invoke:
            def rejected(message):
                with self.assertRaises(ValueError) as error:
                    m.execute(self.s, self.t, self.v, {}, 'demo')
                self.assertEqual(str(error.exception), message)

            rejected('period fixture')
            self.assertEqual(trace, ['period'])
            cg.assert_not_called()
            pg.side_effect = lambda *args: trace.append('period')
            trace.clear()
            rejected('campaign fixture')
            self.assertEqual(trace, ['period', 'campaign'])
            cg.side_effect = lambda *args: trace.append('campaign')
            trace.clear()
            rejected('Paramètre trop long')
            self.assertEqual(trace, ['period', 'campaign'])
            self.v['text'] = ''
            rejected('Connecteur Cloud, detail vide requis')
            invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main()
