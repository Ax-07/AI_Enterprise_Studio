"""Owner-controlled TEST channel provisioning, with durable intent and confirmed revocation."""
import hashlib
import json
import secrets

import acquisition as ac
import acquisition_sync as sync
import business as b
import public_channel as ch

MAX_CHANNELS=3
MAX_DURATION=3600
LIMIT='Canal local TEST uniquement. Aucun mandat réel, paiement, prospect ou dépense.'

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS acquisition_test_channels(
        page TEXT PRIMARY KEY, draft INTEGER NOT NULL REFERENCES acquisition_drafts(id),
        manifest TEXT NOT NULL, manifest_hash TEXT NOT NULL,
        starts INTEGER NOT NULL, expires INTEGER NOT NULL,
        collection TEXT, collection_hash TEXT,
        state TEXT NOT NULL, stop_requested INTEGER, confirmed INTEGER,
        last_error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS acquisition_channel_events(
        id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES acquisition_test_channels(page),
        event TEXT NOT NULL, at INTEGER NOT NULL);""")

def log(c,page,event,t):
    c.execute('INSERT INTO acquisition_channel_events(page,event,at) VALUES(?,?,?)',(page,event,t))

def _row(c,page):
    row=c.execute('SELECT * FROM acquisition_test_channels WHERE page=?',(ch.ident(page),)).fetchone()
    if not row:raise ValueError('Canal TEST absent')
    return row

def _hash(v):
    return hashlib.sha256(ch.canonical(v).encode()).hexdigest()

def _valid(c,row,t):
    return row['starts']<=t<row['expires'] and ac.state(c,ac._row(c,row['draft']))=='draft'

def prepare(c,body,t):
    """Persist publication intent BEFORE any network call. No collection permission."""
    b.fields(body,('draft','snapshot_sha256','duration_seconds'))
    row=ac._row(c,body['draft'])
    if ac.state(c,row)!='draft' or row['snapshot_sha256']!=body['snapshot_sha256']:
        raise ValueError('Brouillon périmé')
    duration=b.integer(body['duration_seconds'],60,MAX_DURATION)
    active=[x for x in c.execute('SELECT * FROM acquisition_test_channels') if x['expires']>t and x['state']!='revoked']
    if len(active)>=MAX_CHANNELS or any(x['draft']==row['id'] for x in active):
        raise ValueError('Un canal par brouillon et trois canaux TEST maximum')
    payload=ac.preview(c,row['id'])
    page=secrets.token_hex(16)
    # No private notes or raw artifacts leave the enterprise, even on loopback.
    m={'id':page,'mode':'test','snapshot':row['snapshot_sha256'],'offer':row['offer'],
       'title':'Démonstration fictive — offre '+str(row['offer']),
       'description':'Parcours de test sans produit livré ni données client.',
       'limitations':'Aucune vente, aucune demande réelle, prix hypothétique.',
       'price_cents':payload['price_cents'],'starts':t,'expires':t+duration}
    c.execute("""INSERT INTO acquisition_test_channels(page,draft,manifest,manifest_hash,starts,expires,state)
                 VALUES(?,?,?,?,?,?,'publication_pending')""",
              (page,row['id'],ch.canonical(m),_hash(m),t,t+duration))
    log(c,page,'publication_intent',t)
    return page,m

def prepare_collection(c,body,t):
    b.fields(body,('page','quota','duration_seconds'))
    row=_row(c,body['page'])
    if row['state']!='published' or row['stop_requested'] is not None or not _valid(c,row,t):
        raise ValueError('Publication TEST confirmée requise')
    duration=b.integer(body['duration_seconds'],1,min(MAX_DURATION,row['expires']-t))
    quota=b.integer(body['quota'],1,1000)
    m=json.loads(row['manifest'])
    g={'page':row['page'],'snapshot':m['snapshot'],'publication_hash':row['manifest_hash'],
       'mode':'test','starts':t,'expires':t+duration,'quota':quota,'notice':ch.NOTICE_VERSION}
    # Bind before the remote call, so no initial signal is lost. Polling is held until confirmed.
    sync.bind(c,{'confirm':True,'draft':row['draft'],'page':row['page'],'snapshot_sha256':m['snapshot'],
                 'duration_seconds':duration,'quota':quota},t)
    c.execute("UPDATE acquisition_test_channels SET collection=?,collection_hash=?,state='collection_pending' WHERE page=?",
              (ch.canonical(g),_hash(g),row['page']))
    log(c,row['page'],'collection_intent',t)
    return row['page'],g

def proof(page,key,request,t):
    nonce=secrets.token_hex(16)
    env=request('status',{'page':page,'nonce':nonce},key)
    ch.exact(env,('payload','signature'))
    p=env['payload']
    ch.exact(p,('page','nonce','mode','at','exists','publication_hash','collection_hash',
                'publication_revoked','collection_revoked','publication_open','collection_open'))
    ch.check(key,'status-v1',p,env['signature'])
    if p['page']!=page or p['nonce']!=nonce or p['mode']!='test':
        raise ValueError('Preuve de canal incompatible')
    ch.integer(p['at'],t-60,t+60)
    for k in ('exists','publication_revoked','collection_revoked','publication_open','collection_open'):
        if type(p[k]) is not bool:raise ValueError('État du canal invalide')
    for k in ('publication_hash','collection_hash'):
        if p[k] is not None:ch.ident(p[k],ch.HEX)
    return p

def request_stop(c,page,t,reason='owner_stop'):
    row=_row(c,page)
    if row['state']=='revoked':return
    if row['stop_requested'] is None:
        c.execute("UPDATE acquisition_test_channels SET stop_requested=?,state='revocation_pending' WHERE page=?",(t,page))
        log(c,page,reason,t)
    if c.execute('SELECT 1 FROM acquisition_test_links WHERE page=?',(page,)).fetchone():
        sync.revoke(c,{'confirm':True,'page':page},t)

def confirm(c,page,p,t):
    row=_row(c,page)
    if row['stop_requested'] is not None:
        if p['publication_revoked'] and p['collection_revoked'] and not p['publication_open'] and not p['collection_open']:
            c.execute("UPDATE acquisition_test_channels SET state='revoked',confirmed=?,last_error='' WHERE page=?",(t,page))
            log(c,page,'remote_revocation_confirmed',t)
            return 'revoked'
        # Absence alone is insufficient; a signed durable revocation tombstone is required.
        return 'revocation_pending'
    if not _valid(c,row,t):
        request_stop(c,page,t,'reference_or_expiry_stop')
        return 'revocation_pending'
    if not p['exists'] or p['publication_hash']!=row['manifest_hash'] or not p['publication_open'] or p['publication_revoked']:
        return row['state']
    target=None
    if row['state']=='publication_pending' and p['collection_hash'] is None and not p['collection_open']:
        target='published'
    if row['state']=='collection_pending' and p['collection_hash']==row['collection_hash'] and p['collection_open'] and not p['collection_revoked']:
        target='collecting'
    if target:
        c.execute('UPDATE acquisition_test_channels SET state=?,confirmed=?,last_error=\'\' WHERE page=?',(target,t,page))
        log(c,page,target,t)
        return target
    return row['state']

def _error(server,page,t):
    with server.db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE acquisition_test_channels SET last_error='confirmation_indisponible' WHERE page=?",(page,))
        request_stop(c,page,t,'unconfirmed_operation')

def _send(request,key,op,domain,payload):
    request(op,{'payload':payload,'signature':ch.sign(key,domain,payload)},key)

def activate(server,body,collection=False,request=None,clock=None):
    """One explicit owner command. Never replay an uncertain activation automatically."""
    request=sync.request_admin if request is None else request
    clock=b.now if clock is None else clock
    key=sync.key()
    with server.db() as c:
        c.execute('BEGIN IMMEDIATE')
        page,payload=(prepare_collection if collection else prepare)(c,body,clock())
    try:
        _send(request,key,'collect' if collection else 'publish','collection-v1' if collection else 'publication-v1',payload)
        p=proof(page,key,request,clock())
        with server.db() as c:
            c.execute('BEGIN IMMEDIATE')
            result=confirm(c,page,p,clock())
        if result!=('collecting' if collection else 'published'):
            raise ValueError('Activation non confirmée')
        return {'page':page,'state':result}
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        _error(server,page,clock())
        return stop_remote(server,page,request=request,clock=clock)

def stop_remote(server,page,request=None,clock=None):
    request=sync.request_admin if request is None else request
    clock=b.now if clock is None else clock
    with server.db() as c:
        c.execute('BEGIN IMMEDIATE')
        request_stop(c,page,clock())
        if _row(c,page)['state']=='revoked':return {'page':page,'state':'revoked'}
    if not sync.configured():return {'page':page,'state':'revocation_pending'}
    try:
        key=sync.key()
        _send(request,key,'revoke','revocation-v1',{'page':page,'scope':'publication'})
        p=proof(page,key,request,clock())
        with server.db() as c:
            c.execute('BEGIN IMMEDIATE')
            result=confirm(c,page,p,clock())
        return {'page':page,'state':result}
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        return {'page':page,'state':'revocation_pending'}

def maintain(server,clock=None,request=None):
    """Never activate in background; only cancel invalid, expired or interrupted operations."""
    clock=b.now if clock is None else clock
    t=clock()
    with server.db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=list(c.execute("SELECT * FROM acquisition_test_channels WHERE state!='revoked' ORDER BY starts"))
        for row in rows:
            if row['stop_requested'] is None and (not _valid(c,row,t) or
                    (row['collection'] and t>=json.loads(row['collection'])['expires']) or
                    (row['state'] in ('publication_pending','collection_pending') and
                     t-(json.loads(row['collection'])['starts'] if row['collection'] else row['starts'])>=60)):
                request_stop(c,row['page'],t,'automatic_safety_stop')
        pages=[r['page'] for r in c.execute("SELECT page FROM acquisition_test_channels WHERE state='revocation_pending' ORDER BY starts")][:MAX_CHANNELS]
    return [stop_remote(server,page,request=request,clock=clock) for page in pages]

def status(c,t=None):
    t=b.now() if t is None else t
    channels=[]
    for row in c.execute('SELECT * FROM acquisition_test_channels ORDER BY starts DESC,page'):
        channels.append({**{k:row[k] for k in ('page','draft','starts','expires','state','stop_requested','confirmed','last_error')},
                         'reference_valid':_valid(c,row,t),'mode':'test',
                         'collection_expires':json.loads(row['collection'])['expires'] if row['collection'] else None})
    return {'channels':channels,'configured':sync.configured(),'mode':'test','limit':LIMIT,
            'events':[dict(x) for x in c.execute('SELECT * FROM acquisition_channel_events ORDER BY id DESC')]}
