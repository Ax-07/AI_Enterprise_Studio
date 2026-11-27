"""Response and retry contracts; all model calls are mocks, never a provider."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core import model_turn


class TokenLimit(RuntimeError):
    pass


class InvalidModelOutput(RuntimeError):
    pass


class ModelTurnTests(unittest.TestCase):
    def setUp(self):
        self.answer = {'action': 'finish', 'target': '', 'text': 'fixture', 'detail': ''}
        self.s = SimpleNamespace(TokenLimit=TokenLimit, InvalidModelOutput=InvalidModelOutput,
                                 call_model=Mock(return_value=self.answer))
        self.t = {'id': 7, 'agent': 'ORION'}
        self.cfg = {'fixture': True}
        self.schema = {'properties': {'action': {'enum': ['finish']}}}
        self.rules = 'fixture rules'
        self.validator = Mock(return_value=True)
        self.prompt = 'fixture prompt'

    def request(self, closing=False, campaign=None):
        return model_turn.request_action(self.s, 1, self.t, self.prompt, self.cfg,
                                         closing, campaign, self.schema,
                                         self.rules, self.validator)

    def check_call(self, call, limit):
        args, kwargs = call
        self.assertEqual((args[0], args[1], args[4], args[5]), (1,self.t['agent'],limit,7))
        self.assertIs(args[3], self.cfg)
        self.assertIs(kwargs['schema'], self.schema)
        self.assertIs(kwargs['validator'], self.validator)
        self.assertEqual(kwargs['rules'], self.rules)

    def test_first_success_calls_once_with_unchanged_contract(self):
        self.assertIs(self.request(), self.answer)
        self.s.call_model.assert_called_once_with(1,'ORION',self.prompt,self.cfg,4096,7,
            schema=self.schema,rules=self.rules,validator=self.validator)

    def test_agent_and_final_turn_output_limits(self):
        for agent, closing, limit in [('ORION',False,4096),('NEXUS',False,8192),
                                      ('NEXUS',True,2048),('ORION',True,2048)]:
            with self.subTest(agent=agent,closing=closing):
                self.t['agent'] = agent
                self.s.call_model.reset_mock()
                self.request(closing)
                call = self.s.call_model.call_args
                self.check_call(call,limit)
                self.assertEqual('DERNIER TOUR' in call.args[2],closing)

    def test_campaign_hint_preserved_only_when_campaign_present(self):
        self.request(campaign={'id': 3})
        self.assertIn('BUDGET ADAPTATIF', self.s.call_model.call_args.args[2])
        self.request(campaign=None)
        self.assertNotIn('BUDGET ADAPTATIF', self.s.call_model.call_args.args[2])

    def test_single_retry_for_each_supported_error(self):
        for error in (TokenLimit('fixture'),InvalidModelOutput('fixture')):
            with self.subTest(error=type(error).__name__):
                self.s.call_model.reset_mock()
                self.s.call_model.side_effect = [error,self.answer]
                self.assertIs(self.request(),self.answer)
                first, second = self.s.call_model.call_args_list
                self.check_call(first,4096)
                self.check_call(second,8192)
                self.assertTrue(second.args[2].startswith(first.args[2]))
                self.assertIn('Tentative de correction unique',second.args[2])

    def test_retry_limits_and_final_turn_hint(self):
        for agent, closing, first_limit, second_limit in [
            ('NEXUS',False,8192,16384),('NEXUS',True,2048,4096)]:
            with self.subTest(agent=agent,closing=closing):
                self.t['agent'] = agent
                self.s.call_model.reset_mock()
                self.s.call_model.side_effect = [TokenLimit('fixture'),self.answer]
                self.request(closing,campaign={'id': 3})
                first, second = self.s.call_model.call_args_list
                self.check_call(first,first_limit)
                self.check_call(second,second_limit)
                self.assertIn('BUDGET ADAPTATIF',second.args[2])
                self.assertEqual('DERNIER TOUR' in second.args[2],closing)

    def test_second_invalid_response_is_terminal_no_third_call(self):
        self.s.call_model.side_effect = [TokenLimit('first'),InvalidModelOutput('second')]
        with self.assertRaises(RuntimeError) as error:
            self.request()
        self.assertEqual(str(error.exception),
                         'second Correction unique épuisée; rapports et fichiers conservés.')
        self.assertEqual(self.s.call_model.call_count,2)

    def test_budget_and_transport_errors_are_not_retried(self):
        for message in ('Budget logiciel insuffisant','Transport non confirmé','Mission arrêtée.'):
            with self.subTest(message=message):
                self.s.call_model.reset_mock()
                self.s.call_model.side_effect = RuntimeError(message)
                with self.assertRaises(RuntimeError) as error:
                    self.request()
                self.assertEqual(str(error.exception),message)
                self.assertEqual(self.s.call_model.call_count,1)

    def test_budget_refusal_during_retry_is_not_swallowed(self):
        refused = RuntimeError('Budget de mission insuffisant')
        self.s.call_model.side_effect = [InvalidModelOutput('fixture'),refused]
        with self.assertRaises(RuntimeError) as error:
            self.request()
        self.assertIs(error.exception,refused)
        self.assertEqual(self.s.call_model.call_count,2)


if __name__ == '__main__':
    unittest.main()
