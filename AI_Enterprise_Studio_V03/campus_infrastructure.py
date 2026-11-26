"""Local technical inventory, no probes, process launches, writes or secret values."""
import json
import re
from pathlib import Path

TABLES=('missions','tasks','reports','artifacts','ledger','connector_runs','connector_policies',
        'connector_workflow_results','incident_recoveries','laboratory_runs','verification_results',
        'campaigns','enterprise_plans','periodic_grants')
MAX_MANIFEST=32768

def manifest(root,name):
    # Exact local filenames only, never follow symbolic links or accept a request path.
    path=Path(root)/name
    try:
        if path.is_symlink() or not path.is_file():return None
        with path.open('rb') as f:raw=f.read(MAX_MANIFEST+1)
        if len(raw)>MAX_MANIFEST:return None
        value=json.loads(raw.decode('utf-8-sig'))
        return value if isinstance(value,dict) else None
    except (OSError,UnicodeError,ValueError,RecursionError):
        return None

def metadata(root,version,cfg,n8n_configured,preview):
    prep=manifest(root,'PREPARATION.json')
    preparation=None
    if prep and prep.get('schema')=='aes.update.preflight.v1':
        preparation={k:prep[k] for k in ('source_unchanged','started','paid_calls','configuration_copied') if type(prep.get(k)) is bool}
        preparation['integrity_recorded']=prep.get('integrity')=='ok'
        preparation['protected_tables']={k:v for k,v in (prep.get('protected_tables') or {}).items() if k in TABLES and type(v) is int and 0<=v<=9007199254740991} if isinstance(prep.get('protected_tables'),dict) else {}
    build=manifest(root,'BUILD_INFO.json')
    commit=build.get('commit') if build else None
    # Build manifest is historical metadata, not proof of checked-out revision.
    if not isinstance(commit,str) or not re.fullmatch(r'[0-9a-f]{40}',commit):commit=None
    return {'version':version,'mode':'preview' if preview else 'operational',
            'openai_configured':bool(cfg.get('key')),'brave_configured':bool(cfg.get('brave')),
            'n8n_configured':bool(n8n_configured),'sandbox_enabled':cfg.get('html_sandbox_enabled') is True,
            'preparation':preparation,'packaged_commit':commit}

def read(db,resources,registry):
    if resources is None:raise ValueError('Inventaire local indisponible')
    existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    page_count=db.execute('PRAGMA page_count').fetchone()[0]
    page_size=db.execute('PRAGMA page_size').fetchone()[0]
    result=[{'kind':'runtime',**{k:resources.get(k) for k in ('version','mode','openai_configured','brave_configured','n8n_configured','sandbox_enabled','packaged_commit','preparation')},
             'database_readable':True,'database_bytes':page_count*page_size,
             'journal_mode':db.execute('PRAGMA journal_mode').fetchone()[0],
             'tables_present':[k for k in TABLES if k in existing],
             'tables_missing':[k for k in TABLES if k not in existing],
             'backup_verified':None,'integrity_verified_now':None}]
    # Read recorded connector metadata only, not diagnostics, secrets or payloads.
    for key,cap in sorted((registry or {}).items()):
        policy=db.execute('SELECT enabled,max_calls,budget FROM connector_policies WHERE capability=?',(key,)).fetchone()
        count,reserved=db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0) FROM connector_runs WHERE capability=?',(key,)).fetchone()
        last=db.execute('SELECT id,state,created,finished FROM connector_runs WHERE capability=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
        result.append({'kind':'connector','id':key,'label':cap['label'],'provider':cap['provider'],
            'implemented':bool(cap['available']),'authorized':bool(policy and policy['enabled']),
            'policy_present':policy is not None,'max_calls':policy['max_calls'] if policy else None,
            'budget':policy['budget'] if policy else None,'calls':count,'reserved':reserved,
            'last':dict(last) if last else None,'availability_verified_now':None})
    return result
