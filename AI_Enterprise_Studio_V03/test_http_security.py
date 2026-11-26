"""HTTP policy regression tests, synthetic tokens only."""
from email.message import Message
import unittest
from infrastructure import security as sec


def headers(**values):
    result = Message()
    for name, value in values.items():
        result[name.replace('_', '-')] = value
    return result


class SecurityTests(unittest.TestCase):
    def test_local_hosts_exact(self):
        for host in ('127.0.0.1:8790', 'localhost:8790'):
            self.assertTrue(sec.local_host(headers(Host=host), 8790))
        for host in ('localhost', 'localhost:8765', 'evil.invalid:8790',
                     '127.0.0.1:8790.evil.invalid', 'LOCALHOST:8790'):
            self.assertFalse(sec.local_host(headers(Host=host), 8790))
        self.assertFalse(sec.local_host(headers(), 8790))

    def test_campus_read_origin_fetch_and_token(self):
        base = {'Host': 'localhost:8790', 'X_Campus_Session': 'fixture-read'}
        self.assertTrue(sec.campus_read_allowed(headers(**base), 'fixture-read'))
        self.assertTrue(sec.campus_read_allowed(headers(**base, Origin='http://localhost:8790',
                                                     Sec_Fetch_Site='same-origin'), 'fixture-read'))
        for extra in ({'Origin': 'http://127.0.0.1:8790'}, {'Origin': 'https://evil.invalid'},
                      {'Sec_Fetch_Site': 'cross-site'}, {'Sec_Fetch_Site': 'none'},
                      {'X_Campus_Session': 'fixture-command'}, {'X_Campus_Session': 'é'}):
            self.assertFalse(sec.campus_read_allowed(headers(**(base | extra)), 'fixture-read'))

    def test_navigation_fetch_policy(self):
        self.assertTrue(sec.direct_navigation_allowed(headers()))
        for value in ('none', 'same-origin'):
            self.assertTrue(sec.direct_navigation_allowed(headers(Sec_Fetch_Site=value)))
        for value in ('same-site', 'cross-site', ''):
            self.assertFalse(sec.direct_navigation_allowed(headers(Sec_Fetch_Site=value)))

    def test_command_requires_matching_origin_json_and_token(self):
        base = {'Host': 'localhost:8790', 'Origin': 'http://localhost:8790',
                'X_Campus_Command': 'fixture-command', 'Content_Type': 'application/json; charset=utf-8'}
        path = '/campus/command'
        self.assertTrue(sec.campus_command_allowed(headers(**base), path, 'fixture-command'))
        self.assertTrue(sec.campus_command_allowed(headers(**(base | {'Content_Type': ' APPLICATION/JSON '})),
                                                  path, 'fixture-command'))
        for extra in ({'Origin': ''}, {'Origin': 'http://127.0.0.1:8790'},
                      {'Sec_Fetch_Site': 'none'}, {'Sec_Fetch_Site': 'cross-site'},
                      {'Content_Type': 'text/plain'}, {'Content_Type': ''},
                      {'X_Campus_Command': 'fixture-read'}):
            self.assertFalse(sec.campus_command_allowed(headers(**(base | extra)), path, 'fixture-command'))
        self.assertFalse(sec.campus_command_allowed(headers(**base), path+'?x=1', 'fixture-command'))
        self.assertFalse(sec.campus_command_allowed(headers(**{k:v for k,v in base.items() if k!='Origin'}),
                                                   path, 'fixture-command'))

    def test_owner_and_command_sessions_are_distinct(self):
        base = {'Host': 'localhost:8790', 'Origin': 'http://localhost:8790',
                'Content_Type': 'application/json', 'X_Campus_Command': 'fixture-command',
                'X_Campus_Owner': 'fixture-owner'}
        self.assertTrue(sec.campus_command_allowed(headers(**base), '/campus/owner-command',
                                                  'fixture-owner', owner=True))
        self.assertFalse(sec.campus_command_allowed(headers(**(base | {'X_Campus_Owner': 'fixture-command'})),
                                                   '/campus/owner-command', 'fixture-owner', owner=True))
        self.assertFalse(sec.campus_command_allowed(headers(**(base | {'X_Campus_Command': 'fixture-owner'})),
                                                   '/campus/command', 'fixture-command'))

    def test_legacy_session_and_origin_compatibility(self):
        base = {'Host': 'localhost:8790', 'X_Session': 'fixture-legacy'}
        self.assertTrue(sec.legacy_session_allowed(headers(**base), 'fixture-legacy'))
        self.assertFalse(sec.legacy_session_allowed(headers(), 'fixture-legacy'))
        self.assertTrue(sec.legacy_command_allowed(headers(**base), 'fixture-legacy', 8790))
        for origin in ('http://localhost:8790', 'http://127.0.0.1:8790'):
            self.assertTrue(sec.legacy_command_allowed(headers(**base, Origin=origin), 'fixture-legacy', 8790))
        for origin in ('https://localhost:8790', 'http://evil.invalid', ''):
            self.assertFalse(sec.legacy_command_allowed(headers(**base, Origin=origin), 'fixture-legacy', 8790))
        self.assertFalse(sec.legacy_command_allowed(headers(**base), 'fixture-other', 8790))


if __name__ == '__main__':
    unittest.main()
