"""CI-only guard: prove candidate ZIP and prepared public files match Git HEAD."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import zipfile

import release_metadata
import release_paths

ROOT = Path(__file__).resolve().parent
PREFIX = 'AI_Enterprise_Studio_V03/'
BASELINE_SCHEMA = 'aes.release.baseline.v1'


def git(root, *args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
               GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output(['git', *args], cwd=root, env=env)


def baseline_names(path):
    data = json.loads(Path(path).read_bytes())
    if (not isinstance(data, dict) or set(data) != {'schema', 'commit', 'paths'}
            or data['schema'] != BASELINE_SCHEMA or not isinstance(data['commit'], str)
            or len(data['commit']) != 40 or any(c not in '0123456789abcdef' for c in data['commit'])
            or not isinstance(data['paths'], list) or not data['paths']):
        raise ValueError('Invalid release baseline')
    names = data['paths']
    for name in names:
        release_paths.parts_for(name)
    if len(set(names)) != len(names) or 'BUILD_INFO.json' in names:
        raise ValueError('Invalid release baseline paths')
    return set(names)


def committed_files(root):
    prefix = git(root, 'rev-parse', '--show-prefix').decode('utf-8').strip()
    repo = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel').rstrip(b'\r\n')))
    commit = git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    entries = git(repo, 'ls-tree', '-r', '-z', commit, '--', prefix or '.')
    files = {}
    for record in entries.split(b'\0'):
        if not record:
            continue
        meta, encoded = record.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        full = encoded.decode('utf-8')
        if prefix and not full.startswith(prefix):
            raise ValueError('Unexpected Git path')
        name = full[len(prefix):]
        if release_paths.allowed(name):
            if kind != 'blob' or mode not in ('100644', '100755') or name in files:
                raise ValueError('Invalid committed runtime entry')
            files[name] = oid
    release_paths.checked_names(files)
    return repo, commit, files


def verify_archive(archive, root=ROOT, baseline=None):
    root = Path(root)
    baseline = root / 'release_baseline.json' if baseline is None else Path(baseline)
    repo, commit, files = committed_files(root)
    historical = baseline_names(baseline)
    missing = historical - set(files)
    if missing:
        raise ValueError('Historical runtime paths missing: '+', '.join(sorted(missing)))
    expected = set(files) | {'BUILD_INFO.json'}
    hashes = {}
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        if len(names) != len(set(names)) or set(names) != {PREFIX+n for n in expected}:
            raise ValueError('ZIP file set differs from committed release policy')
        for entry in entries:
            if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Invalid ZIP entry type')
        for name, oid in sorted(files.items()):
            expected_bytes = git(repo, 'cat-file', 'blob', oid)
            actual = z.read(PREFIX+name)
            if actual != expected_bytes:
                raise ValueError('ZIP content differs from committed blob: '+name)
            hashes[name] = hashlib.sha256(actual).hexdigest()
        metadata = release_metadata.build_info(
            z.read(PREFIX+'release_version.json'), z.read(PREFIX+'serveur.py'), commit)
        raw = z.read(PREFIX+'BUILD_INFO.json')
        if json.loads(raw) != metadata:
            raise ValueError('ZIP build metadata does not match committed release')
        hashes['BUILD_INFO.json'] = hashlib.sha256(raw).hexdigest()
    return {'commit': commit, 'historical_paths': len(historical), 'files': hashes}


def verify_installation(target, report):
    target = Path(target)
    hashes = report['files']
    if set(release_paths.runtime_files(target)) != set(hashes):
        raise ValueError('Prepared runtime file set differs from verified ZIP')
    for name, expected in hashes.items():
        if release_paths.file_type(target/name) != 'file':
            raise ValueError('Prepared runtime file is not regular')
        if hashlib.sha256((target/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Prepared runtime file differs from verified ZIP: '+name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--installed', type=Path)
    args = parser.parse_args()
    report = verify_archive(args.archive)
    if args.installed:
        verify_installation(args.installed, report)
    print(json.dumps({'commit': report['commit'], 'historical_paths': report['historical_paths'],
                      'verified_public_files': len(report['files']),
                      'prepared_copy_verified': args.installed is not None}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
