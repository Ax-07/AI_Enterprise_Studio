"""Provider protocol contracts; no network or real credentials."""
import json
import unittest
from unittest.mock import MagicMock, patch

from infrastructure import providers as p


class ProviderTests(unittest.TestCase):
    def test_http_json_request(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        with patch.object(p.urllib.request, 'urlopen', return_value=response) as open_url:
            result = p.request_json('https://api.openai.com/v1/responses',
                                    {'Authorization': 'Bearer fixture'}, {'input': 'é'})
        self.assertEqual(result, {'ok': True})
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.data, '{"input": "é"}'.encode())
        self.assertEqual(open_url.call_args.kwargs, {'timeout': 120})
        response.__enter__.return_value.read.assert_called_once_with(2_000_000)

    def test_http_get_without_body(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch.object(p.urllib.request, 'urlopen', return_value=response) as open_url:
            self.assertEqual(p.request_json('https://api.search.brave.com/res/v1/web/search',
                                           {'X-Subscription-Token': 'fixture'}), {})
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('X-subscription-token'), 'fixture')

    def test_responses_payload_default_and_custom_schema(self):
        schema = {'type': 'object'}
        report = p.responses_payload('model', 'prompt', 8192, 'rules', schema)
        self.assertEqual(report['model'], 'model')
        self.assertEqual(report['input'], 'prompt')
        self.assertEqual(report['max_output_tokens'], 8192)
        self.assertFalse(report['store'])
        self.assertTrue(report['instructions'].startswith('rules Réponds en français.'))
        self.assertEqual(report['text']['format'], {'type': 'json_schema',
                         'name': 'rapport', 'strict': True, 'schema': schema})
        action = p.responses_payload('model', 'prompt', 1024, 'rules', schema,
                                     schema={'type': 'array'}, rules='action rules')
        self.assertEqual(action['instructions'], 'action rules')
        self.assertEqual(action['text']['format'], {'type': 'json_schema',
                         'name': 'action_agent', 'strict': True, 'schema': {'type': 'array'}})

    def test_usage_and_status_metadata(self):
        response = {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                    'usage': {'input_tokens': 10, 'output_tokens': 20,
                              'output_tokens_details': {'reasoning_tokens': 3}}}
        self.assertEqual(p.response_usage(response),
                         (10, 20, 3, 'max_output_tokens', 'incomplete', False,
                          'incomplete / max_output_tokens'))
        self.assertEqual(p.response_usage({}), (None, None, None, None, 'absent', False, 'absent'))
        self.assertEqual(p.response_usage({'usage': {'output_tokens_details': {'reasoning_tokens': -1}}})[2], None)
        refused = {'status': 'completed', 'output': [{'type': 'message',
                    'content': [{'type': 'refusal', 'refusal': 'fixture'}]}]}
        self.assertEqual(p.response_usage(refused)[-2:], (True, 'refusal'))

    def test_text_segments_preserve_order(self):
        response = {'output': [{'type': 'reasoning', 'content': [{'type': 'output_text', 'text': 'ignored'}]},
                    {'type': 'message', 'content': [{'type': 'output_text', 'text': '{"ok":'},
                                                  {'type': 'output_text', 'text': None},
                                                  {'type': 'refusal', 'text': 'ignored'}]},
                    {'type': 'message', 'content': [{'type': 'output_text', 'text': 'true}'}]}]}
        self.assertEqual(json.loads(p.response_text(response)), {'ok': True})
        self.assertEqual(p.response_text({}), '')


if __name__ == '__main__':
    unittest.main()
