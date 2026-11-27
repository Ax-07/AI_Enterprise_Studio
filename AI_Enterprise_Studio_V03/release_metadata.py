"""Validate public release metadata without importing the engine."""
import ast
import json
import re

SCHEMA = 'aes.release.version.v1'
BUILD_SCHEMA = 'aes.release.build.v1'
FIELDS = frozenset(('schema', 'engine_version', 'release_version', 'phase', 'status'))


def read_version(data):
    value = json.loads(data)
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Métadonnées de version invalides')
    if value['schema'] != SCHEMA or value['status'] not in ('candidate', 'stable'):
        raise ValueError('Schéma ou statut de livraison invalide')
    for key in ('engine_version', 'release_version'):
        if not isinstance(value[key], str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value[key]):
            raise ValueError('Version de livraison invalide')
    if not isinstance(value['phase'], str) or not re.fullmatch(r'R[0-9]{2}(?:\.[0-9]+)*', value['phase']):
        raise ValueError('Phase de livraison invalide')
    if tuple(map(int, value['release_version'].split('.'))) < tuple(map(int, value['engine_version'].split('.'))):
        raise ValueError('Cycle antérieur à la version moteur')
    return value


def engine_version(source):
    tree = ast.parse(source)
    assignments = [node.value for node in tree.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'VERSION'
                           for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('Version moteur statique introuvable ou ambiguë')
    value = ast.literal_eval(assignments[0])
    if not isinstance(value, str):
        raise ValueError('Version moteur invalide')
    return value


def build_info(version_data, server_source, commit):
    value = read_version(version_data)
    if value['engine_version'] != engine_version(server_source):
        raise ValueError('Incohérence entre manifeste et moteur')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Révision Git invalide')
    return {
        'schema': BUILD_SCHEMA,
        'candidate': 'V'+value['release_version'],
        'version': value['engine_version'],
        'engine_version': value['engine_version'],
        'release_version': value['release_version'],
        'phase': value['phase'],
        'status': value['status'],
        'commit': commit,
        'contains_local_data': False,
    }
