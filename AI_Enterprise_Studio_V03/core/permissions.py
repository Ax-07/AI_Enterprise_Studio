"""Permanent agent permissions. Operational authorization remains in the engine.

Connector and commercial grants are supplied by their authoritative registries;
this module neither imports them nor grants campaign or budget authorization.
"""


def build_permissions(agent_ids, connector_roles, commercial_actions):
    """Return a fresh legacy-compatible map of agent IDs to mutable sets."""
    perms = {a: {'finish', 'memory', 'request', 'read_report'} for a in agent_ids}
    for a in ('ATLAS', 'ORION', 'MIDAS', 'HERMES', 'SENTINEL', 'PROMETHEUS'):
        perms[a] |= {'search', 'read'}
    perms['ATLAS'] |= {'delegate', 'opportunity', 'calculate', 'list_files', 'read_file'}
    perms['ORION'] |= {'opportunity', 'calculate'}
    perms['MIDAS'] |= {'calculate', 'list_files', 'read_file', 'assess_opportunity'}
    perms['NEXUS'] |= {'write_file', 'list_files', 'read_file', 'check_file', 'calculate', 'search', 'read'}
    perms['HERMES'] |= {'write_file', 'list_files', 'read_file', 'calculate'}
    perms['SENTINEL'] |= {'check_file', 'list_files', 'read_file', 'calculate'}
    perms['PROMETHEUS'] |= {'list_files', 'read_file', 'calculate'}
    perms['MNEMOS'] |= {'list_files', 'read_file'}
    for a in ('NEXUS', 'SENTINEL'):
        perms[a].add('test_file')
    for a in connector_roles:
        perms[a].add('connector')
    for action, agent in commercial_actions.items():
        perms[agent].add(action)
    return perms


def require_action(perms, agent, action):
    """Check the permanent grant only; preserve the legacy exception contract."""
    if action not in perms[agent]:
        raise ValueError('Outil interdit à ' + agent)
