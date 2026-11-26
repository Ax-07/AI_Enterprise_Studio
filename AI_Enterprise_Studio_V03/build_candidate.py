"""Build a public-runtime ZIP from committed Git blobs, never local data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import release_paths as paths
import release_metadata

ROOT = Path(__file__).resolve().parent


def git(cwd, *args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
               GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output(['git', *args], cwd=cwd, env=env)


def build(dest, root=None):
    root = Path(root) if root is not None else ROOT
    prefix = git(root, 'rev-parse', '--show-prefix').decode('utf-8').strip()
    repo = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel').rstrip(b'\r\n')))
    revision = git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    raw = git(repo, 'ls-tree', '-r', '-z', revision, '--', prefix or '.')
    selected = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        meta, encoded = record.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        name = encoded.decode('utf-8')
        if prefix and not name.startswith(prefix):
            raise ValueError('Chemin Git inattendu')
        name = name[len(prefix):]
        if not paths.allowed(name):
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Fichier suivi non régulier dans le paquet')
        if name in selected:
            raise ValueError('Chemin Git dupliqué')
        selected[name] = oid
    names = paths.checked_names(selected)
    metadata = release_metadata.build_info(
        git(repo, 'cat-file', 'blob', selected['release_version.json']),
        git(repo, 'cat-file', 'blob', selected['serveur.py']), revision)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in names:
            data = git(repo, 'cat-file', 'blob', selected[name])
            z.writestr('AI_Enterprise_Studio_V03/'+name, data)
        z.writestr('AI_Enterprise_Studio_V03/BUILD_INFO.json', json.dumps(metadata, indent=2))
    print('SHA256 '+hashlib.sha256(dest.read_bytes()).hexdigest()+'  '+dest.name)


if __name__ == '__main__':
    build(sys.argv[1])
