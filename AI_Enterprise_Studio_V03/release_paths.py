"""Shared public-runtime path policy for build and offline preparation.

A path allowlist is not a content-based secret scanner. Only reviewed public
source belongs in these directories. Never add local configuration here.
"""
from pathlib import Path, PurePosixPath
import os
import stat

CODE_DIRS = frozenset(('core', 'departments', 'tools', 'infrastructure', 'api', 'bootstrap'))
PUBLIC_DIRS = CODE_DIRS | frozenset(('interface', 'sandbox', 'n8n', 'docs'))
PRIVATE_DIRS = frozenset(('donnees', 'archives', 'backups', 'secrets', 'credentials',
                          'tests', '__pycache__', 'venv', 'node_modules'))
PRIVATE_NAMES = frozenset(('config.json', 'preparation.json', 'credentials.json',
                           'secrets.json', 'settings.local.json'))
ROOT_SUFFIXES = frozenset(('.py', '.html', '.md', '.bat', '.ps1', '.sh'))
ROOT_TEXT = frozenset(('INSTALLATION.txt', 'Lisez-moi.txt'))
ASSET_SUFFIXES = {
    'interface': frozenset(('.html', '.css', '.js', '.json', '.webp', '.png',
                            '.jpg', '.jpeg', '.svg', '.ico', '.woff', '.woff2')),
    'sandbox': frozenset(('.py', '.txt', '.sh')),
    'n8n': frozenset(('.json', '.yaml', '.yml', '.txt', '.md')),
    'docs': frozenset(('.md', '.txt')),
}
REQUIRED = frozenset(('serveur.py', 'index.html', 'prepare_update.py',
                      'release_paths.py', 'LANCER_CAMPUS.bat', 'LANCER_APERCU.bat',
                      'preview_campus.py', 'interface/live.html', 'interface/manifest.json'))
_RESERVED = frozenset(('con', 'prn', 'aux', 'nul', 'conin$', 'conout$') +
                      tuple('com'+str(i) for i in range(1, 10)) +
                      tuple('lpt'+str(i) for i in range(1, 10)))


def parts_for(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Chemin de livraison invalide')
    parts = name.split('/')
    if any(not part or part in ('.', '..') or part.endswith(('.', ' '))
           or any(ord(c) < 32 or c in ':*?"<>|' for c in part)
           or part.split('.')[0].casefold() in _RESERVED for part in parts):
        raise ValueError('Chemin de livraison invalide')
    return parts


def excluded(parts):
    lower = [p.casefold() for p in parts]
    return (any(p in PRIVATE_DIRS or p.startswith('.') for p in lower)
            or lower[-1] in PRIVATE_NAMES
            or lower[-1].startswith(('test_', 'smoke_')))


def allowed(name, *, metadata=False):
    parts = parts_for(name)
    if excluded(parts):
        return False
    p = PurePosixPath(name)
    if len(parts) == 1:
        return (p.suffix in ROOT_SUFFIXES or name in ROOT_TEXT
                or (metadata and name == 'BUILD_INFO.json'))
    top = parts[0]
    if top in CODE_DIRS:
        return p.suffix == '.py' and all(x.isidentifier() for x in parts[1:-1])
    if top == 'sandbox' and name == 'sandbox/Dockerfile':
        return True
    return p.suffix in ASSET_SUFFIXES.get(top, ())


def checked_names(names):
    names = sorted(names)
    seen = {}
    for name in names:
        parts = parts_for(name)
        for i in range(1, len(parts)+1):
            prefix = '/'.join(parts[:i])
            key = prefix.casefold()
            if key in seen and seen[key] != prefix:
                raise ValueError('Collision de chemins (Windows)')
            seen[key] = prefix
    if len(names) != len(set(names)):
        raise ValueError('Chemin dupliqué')
    missing = REQUIRED - set(names)
    if missing:
        raise ValueError('Paquet incomplet : '+', '.join(sorted(missing)))
    return names


def file_type(path):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('Lien ou point de réanalyse non autorisé dans le paquet')
    if stat.S_ISDIR(info.st_mode):
        return 'directory'
    if stat.S_ISREG(info.st_mode):
        return 'file'
    raise ValueError('Type de fichier non autorisé dans le paquet')


def runtime_files(candidate):
    """Directory copy mode: only allowlisted files, no traversal of private dirs."""
    candidate = Path(candidate)
    if file_type(candidate) != 'directory':
        raise ValueError('Dossier candidat invalide')
    selected = []

    def walk(directory, prefix):
        for entry in sorted(directory.iterdir()):
            name = prefix + entry.name
            parts = parts_for(name)
            if excluded(parts):
                continue
            if not prefix and entry.name not in PUBLIC_DIRS and not allowed(name, metadata=True):
                continue
            kind = file_type(entry)
            if kind == 'directory':
                if prefix or entry.name in PUBLIC_DIRS:
                    walk(entry, name+'/')
            elif allowed(name, metadata=True):
                selected.append(name)

    walk(candidate, '')
    return checked_names(selected)
