"""Local HTTP access predicates. No business permissions or session storage."""
import secrets
import urllib.parse


def local_host(headers, port):
    return headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')


def campus_read_allowed(headers, token):
    # Caller must already have checked the local Host.
    return (secrets.compare_digest(headers.get('X-Campus-Session', '').encode(), token.encode())
            and headers.get('Origin') in (None, 'http://'+headers.get('Host', ''))
            and headers.get('Sec-Fetch-Site') in (None, 'same-origin'))


def direct_navigation_allowed(headers):
    # Caller must already have checked the local Host.
    return headers.get('Sec-Fetch-Site') in (None, 'none', 'same-origin')


def legacy_session_allowed(headers, token):
    # Caller must already have checked the local Host.
    return headers.get('X-Session') == token


def campus_command_allowed(headers, path, token, *, owner=False):
    # Caller must already have checked the local Host.
    return (secrets.compare_digest(headers.get('X-Campus-Owner' if owner else 'X-Campus-Command', '').encode(), token.encode())
            and headers.get('Origin') == 'http://'+headers.get('Host', '')
            and headers.get('Sec-Fetch-Site') in (None, 'same-origin')
            and headers.get('Content-Type', '').split(';', 1)[0].strip().lower() == 'application/json'
            and not urllib.parse.urlsplit(path).query)


def legacy_command_allowed(headers, token, port):
    # Preserve legacy allowance for either local origin, or no Origin.
    return (legacy_session_allowed(headers, token)
            and headers.get('Origin') in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}'))
