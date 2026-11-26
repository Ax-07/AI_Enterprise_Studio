"""Local TEST acquisition reconciliation. No live leads, business trials or agent permissions."""
import hashlib
import http.client
import json
import os
import re

import acquisition
import acquisition_runtime
import business
import public_channel as ch
import n8n_bridge

MAX_BYTES=512*1024
FRESHNESS=120
POLL_SECONDS=60
MAX_ACTIVE_LINKS=3
LIMIT='Signaux TEST uniquement; intentions autodéclarées, aucune commande, aucun prospect réel ni observation commerciale.'

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS acquisition_test_links(
        page TEXT PRIMARY KEY, draft INTEGER NOT NULL REFERENCES acquisition_drafts(id),
        snapshot TEXT NOT NULL, starts INTEGER NOT NULL, expires INTEGER NOT NULL,
        quota INTEGER NOT NULL, revoked INTEGER, last_export INTEGER,
        last_digest TEXT, accepted_total INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS acquisition_test_signals(
        page TEXT NOT NULL REFERENCES acquisition_test_links(page),
        event_hash TEXT NOT NULL, participant_hash TEXT NOT NULL,
        kind TEXT NOT NULL, segment INTEGER NOT NULL, observed INTEGER NOT NULL,
        PRIMARY KEY(page,event_hash), UNIQUE(page,participant_hash));""")

def bind(c,b,t=None):
    t=business.now() if t is None else t
    business.fields(b,('draft','page','snapshot_sha256','duration_seconds','quota'))
    row=acquisition._row(c,b['draft'])
    if acquisition.state(c,row)!='draft' or b['snapshot_sha256']!=row['snapshot_sha256']:
        raise ValueError('Brouillon périmé ou révoqué')
    page=ch.ident(b['page'])
    duration=business.integer(b['duration_seconds'],1,ch.MAX_LIFETIME)
    quota=business.integer(b['quota'],1,1000)
    active=[x for x in c.execute('SELECT * FROM acquisition_test_links') if state(c,x,t)=='test_link']
    if len(active)>=MAX_ACTIVE_LINKS or any(x['draft']==row['id'] for x in active):
        raise ValueError('Liaisons TEST actives limitées; une par brouillon')
    if c.execute('SELECT 1 FROM acquisition_test_links WHERE page=?',(page,)).fetchone():
        raise ValueError('Canal de test déjà lié; historique conservé')
    c.execute('INSERT INTO acquisition_test_links(page,draft,snapshot,starts,expires,quota) VALUES(?,?,?,?,?,?)',
              (page,row['id'],row['snapshot_sha256'],t,t+duration,quota))
    return page

def link(c,page):
    row=c.execute('SELECT * FROM acquisition_test_links WHERE page=?',(ch.ident(page),)).fetchone()
    if not row:raise ValueError('Liaison TEST absente')
    return row

def state(c,row,t):
    if row['revoked'] is not None:return 'revoked'
    if not row['starts']<=t<row['expires']:return 'inactive'
    if acquisition.state(c,acquisition._row(c,row['draft']))!='draft':return 'reference_changed'
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='acquisition_test_channels'").fetchone():
        managed=c.execute('SELECT state FROM acquisition_test_channels WHERE page=?',(row['page'],)).fetchone()
        if managed and managed['state']!='collecting':return 'awaiting_control'
    return 'test_link'

def revoke(c,b,t=None):
    t=business.now() if t is None else t
    business.fields(b,('page',))
    row=link(c,b['page'])
    c.execute('UPDATE acquisition_test_links SET revoked=COALESCE(revoked,?) WHERE page=?',(t,row['page']))
    c.execute('DELETE FROM acquisition_test_signals WHERE page=?',(row['page'],))
    return row['page']

def purge(c,t):
    c.execute('DELETE FROM acquisition_test_signals WHERE observed<=?',(t-ch.RETENTION,))
    for row in c.execute('SELECT * FROM acquisition_test_links'):
        if state(c,row,t)!='test_link':
            c.execute('DELETE FROM acquisition_test_signals WHERE page=?',(row['page'],))

def _hash(v):
    return hashlib.sha256(v.encode('ascii')).hexdigest()

def qualify(kind,segment):
    """HERMES rule v1: self-declared target fit AND demo intent, not verified person."""
    return kind=='demo_request' and segment is True

def ingest(c,key,page,envelope,t=None):
    """Use under BEGIN IMMEDIATE. Full signed snapshot, not an append-only lead feed."""
    t=business.now() if t is None else t
    row=link(c,page)
    if state(c,row,t)!='test_link':raise ValueError('Liaison TEST inactive')
    ch.exact(envelope,('payload','signature'))
    payload=envelope['payload']
    ch.exact(payload,('page','snapshot','mode','exported','accepted_total','signals','paid_orders'))
    ch.check(key,'export-v1',payload,envelope['signature'])
    if payload['page']!=page or payload['snapshot']!=row['snapshot'] or payload['mode']!='test':
        raise ValueError('Canal, mode ou empreinte incompatibles')
    ch.integer(payload['paid_orders'],0,0)
    stamp=ch.integer(payload['exported'],max(row['starts'],t-FRESHNESS),t)
    total=ch.integer(payload['accepted_total'],row['accepted_total'],row['quota'])
    sig=business.digest(payload)
    if row['last_export'] is not None:
        if stamp<row['last_export']:raise ValueError('Export antérieur refusé')
        if stamp==row['last_export']:
            if sig==row['last_digest']:return {'replayed':True}
            raise ValueError('Deux états au même instant; prochain export requis')
    items=payload['signals']
    if not isinstance(items,list) or len(items)>total:raise ValueError('Nombre de signaux invalide')
    events=set();participants=set();validated=[]
    for x in items:
        ch.exact(x,('id','participant','kind','segment','observed','notice'))
        event=ch.ident(x['id']);part=ch.ident(x['participant'],ch.HEX)
        if event in events or part in participants:raise ValueError('Doublon dans export')
        events.add(event);participants.add(part)
        if x['kind'] not in ch.KINDS or type(x['segment']) is not bool or x['notice']!=ch.NOTICE_VERSION:
            raise ValueError('Signal invalide')
        observed=ch.integer(x['observed'],max(row['starts'],t-ch.RETENTION+1),min(stamp,row['expires']-1))
        validated.append((page,_hash(event),_hash(part),x['kind'],int(x['segment']),observed))
    # All validation occurs before replacing the previous complete snapshot.
    # Removal from an authenticated newer export propagates withdrawal/expiry.
    c.execute('DELETE FROM acquisition_test_signals WHERE page=?',(page,))
    c.executemany('INSERT INTO acquisition_test_signals VALUES(?,?,?,?,?,?)',validated)
    c.execute('UPDATE acquisition_test_links SET last_export=?,last_digest=?,accepted_total=? WHERE page=?',
              (stamp,sig,total,page))
    return {'replayed':False,'signals':len(validated)}

def configured():
    if acquisition_runtime.managed():return acquisition_runtime.runtime_key() is not None
    return bool(re.fullmatch(r'[0-9a-fA-F]{64}',os.environ.get('AES_CHANNEL_TEST_KEY_HEX','')))

def key():
    if acquisition_runtime.managed():
        value=acquisition_runtime.runtime_key()
        if value is None:raise ValueError('Service TEST autonome indisponible')
        return value
    if not configured():raise ValueError('Clé de canal TEST non configurée')
    return bytes.fromhex(os.environ['AES_CHANNEL_TEST_KEY_HEX'])

def request_admin(operation,body,k):
    """Fixed loopback transport, no redirect, no n8n or paid provider credentials."""
    if operation not in ('export','status','publish','collect','revoke'):
        raise ValueError('Opération TEST interdite')
    auth=ch.sign(k,'admin-bearer-v1',{'service':'test-only'})
    conn=http.client.HTTPConnection('127.0.0.1',8765,timeout=5)
    try:
        conn.request('POST','/admin/'+operation,body=ch.canonical(body).encode(),
                     headers={'Authorization':'Bearer '+auth,'Content-Type':'application/json','Connection':'close'})
        res=conn.getresponse()
        if res.status!=200:raise ValueError('Canal TEST indisponible')
        raw=res.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('Export TEST trop volumineux')
        return n8n_bridge.decode(raw)
    except (OSError,http.client.HTTPException,UnicodeError,RecursionError):
        raise ValueError('Transport TEST indisponible') from None
    finally:conn.close()

def fetch(page,k):
    ch.ident(page)
    return request_admin('export',{'page':page},k)

def run_once(server,t=None,transport=None):
    """Bounded test-only polling, no work if owner has not bound an active page."""
    t=business.now() if t is None else t
    transport=fetch if transport is None else transport
    with server.db() as c:
        c.execute('BEGIN IMMEDIATE')
        purge(c,t)
        pages=[r['page'] for r in c.execute('SELECT * FROM acquisition_test_links ORDER BY starts,page')
               if state(c,r,t)=='test_link' and
               (r['last_export'] is None or t-r['last_export']>=POLL_SECONDS)][:MAX_ACTIVE_LINKS]
    if not configured():return []
    k=key()
    results=[]
    for page in pages:
        try:
            envelope=transport(page,k)
            with server.db() as c:
                c.execute('BEGIN IMMEDIATE')
                result=ingest(c,k,page,envelope,business.now())
            results.append({'page':page,'ok':True,**result})
        except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
            results.append({'page':page,'ok':False})
    return results

def loop(server,shutdown):
    # Never call at startup. Explicit link authorizes TEST polling only.
    while not shutdown.wait(POLL_SECONDS):
        try:run_once(server)
        except Exception as exc:
            # Log class only: never payload, credentials or participant data.
            print('[ACQUISITION TEST] '+type(exc).__name__,flush=True)

def status(c,t=None):
    t=business.now() if t is None else t
    links=[]
    for row in c.execute('SELECT * FROM acquisition_test_links ORDER BY starts DESC,page'):
        active=state(c,row,t)
        fresh=active=='test_link' and row['last_export'] is not None and 0<=t-row['last_export']<=FRESHNESS
        # Never present stale or inactive data as current.
        rows=list(c.execute('SELECT * FROM acquisition_test_signals WHERE page=? AND observed>?',
                            (row['page'],t-ch.RETENTION))) if fresh else []
        counts={kind:sum(x['kind']==kind for x in rows) for kind in ch.KINDS}
        links.append({**{k:row[k] for k in ('page','draft','snapshot','starts','expires','quota','last_export','accepted_total')},
                      'state':active,'fresh':fresh,'test_signals':len(rows),'intents':counts,
                      'qualified_test':sum(qualify(x['kind'],bool(x['segment'])) for x in rows)})
    return {'mode':'test','configured':configured(),'links':links,'qualification_rule':'hermes-test-v1','poll_seconds':POLL_SECONDS,
            'real_prospects':0,'paid_orders':0,'external_spend_cents':0,'limit':LIMIT}
