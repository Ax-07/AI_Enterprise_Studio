"""Isolated acquisition channel core. Standard library only; no enterprise imports.

Test-only until deployment, privacy notice and end-to-end owner authorization are validated.
Never put this database in the enterprise data directory. No contacts, IPs or raw tokens stored.
"""
import hashlib
import hmac
import html
import json
import re
import secrets
import sqlite3
import time

MAX_LIFETIME=86400
RETENTION=7*86400
NOTICE_VERSION='test-anonymous-v1'
KINDS=('interest','demo_request','purchase_question')
HEX=re.compile(r'[0-9a-f]{64}\Z')
ID=re.compile(r'[0-9a-f]{32}\Z')

def canonical(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def sign(key,domain,payload):
    if not isinstance(key,bytes) or len(key)<32:
        raise ValueError('Channel key must contain at least 32 bytes')
    return hmac.new(key,(domain+'\n'+canonical(payload)).encode('utf8'),hashlib.sha256).hexdigest()

def check(key,domain,payload,signature):
    if not isinstance(signature,str) or not hmac.compare_digest(sign(key,domain,payload),signature):
        raise ValueError('Invalid signature')

def exact(b,keys):
    if not isinstance(b,dict) or set(b)!=set(keys):
        raise ValueError('Unexpected fields')

def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:raise ValueError('Invalid integer')
    return v

def text(v,n):
    if not isinstance(v,str) or not 1<=len(v.strip())<=n:
        raise ValueError('Invalid text')
    return v.strip()

def ident(v,pattern=ID):
    if not isinstance(v,str) or not pattern.fullmatch(v):raise ValueError('Invalid identifier')
    return v

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS channel_pages(
        id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, manifest TEXT NOT NULL,
        starts INTEGER NOT NULL, expires INTEGER NOT NULL, revoked INTEGER,
        collection TEXT, collection_revoked INTEGER, accepted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS channel_revoked_pages(id TEXT PRIMARY KEY, revoked INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS channel_signals(
        id TEXT PRIMARY KEY, page TEXT NOT NULL REFERENCES channel_pages(id),
        participant TEXT NOT NULL, kind TEXT NOT NULL, segment INTEGER NOT NULL,
        observed INTEGER NOT NULL, notice TEXT NOT NULL, delete_hash TEXT NOT NULL,
        UNIQUE(page,participant));
    CREATE TABLE IF NOT EXISTS channel_tombstones(
        page TEXT NOT NULL, participant TEXT NOT NULL, expires INTEGER NOT NULL,
        PRIMARY KEY(page,participant));""")

def _row(c,page):
    row=c.execute('SELECT * FROM channel_pages WHERE id=?',(ident(page),)).fetchone()
    if not row:raise ValueError('Page unavailable')
    return row

def _publication(m,t):
    exact(m,('id','mode','snapshot','offer','title','description','limitations','price_cents','starts','expires'))
    ident(m['id']);ident(m['snapshot'],HEX)
    if m['mode']!='test':raise ValueError('Live deployment disabled')
    integer(m['offer'],1,2**53-1)
    integer(m['starts'],t-60,t+60)
    integer(m['expires'],max(t+1,m['starts']+1),m['starts']+MAX_LIFETIME)
    for k,n in (('title',180),('description',2000),('limitations',2000)):
        text(m[k],n)
    integer(m['price_cents'],1,100000000)

def publish(c,key,m,signature,t):
    """Separate signed publication grant, no collection permission."""
    check(key,'publication-v1',m,signature);_publication(m,t)
    if c.execute('SELECT 1 FROM channel_revoked_pages WHERE id=?',(m['id'],)).fetchone():
        raise ValueError('Publication revoked')
    old=c.execute('SELECT * FROM channel_pages WHERE id=?',(m['id'],)).fetchone()
    if old:
        if old['manifest']==canonical(m) and old['revoked'] is None:return m['id']
        raise ValueError('Publication already exists or revoked')
    c.execute('INSERT INTO channel_pages(id,snapshot,manifest,starts,expires) VALUES(?,?,?,?,?)',
              (m['id'],m['snapshot'],canonical(m),m['starts'],m['expires']))
    return m['id']

def _active(row,t):
    return row['revoked'] is None and row['starts']<=t<row['expires']

def authorize_collection(c,key,g,signature,t):
    """Second signed grant, bound to exact public content and offer snapshot."""
    check(key,'collection-v1',g,signature)
    exact(g,('page','snapshot','publication_hash','mode','starts','expires','quota','notice'))
    row=_row(c,g['page'])
    if not _active(row,t) or row['collection_revoked'] is not None or g['mode']!='test' or g['snapshot']!=row['snapshot']:
        raise ValueError('Publication not ready')
    if g['publication_hash']!=hashlib.sha256(row['manifest'].encode()).hexdigest():
        raise ValueError('Publication content changed')
    if g['notice']!=NOTICE_VERSION:raise ValueError('Notice mismatch')
    integer(g['starts'],t,min(row['expires']-1,t+60))
    integer(g['expires'],g['starts']+1,row['expires'])
    integer(g['quota'],1,1000)
    if row['collection'] is not None:
        if row['collection']==canonical(g) and row['collection_revoked'] is None:return g['page']
        raise ValueError('Collection already authorized or revoked')
    c.execute('UPDATE channel_pages SET collection=? WHERE id=?',(canonical(g),g['page']))
    return g['page']

def _collection(row,t):
    if not _active(row,t) or row['collection_revoked'] is not None or not row['collection']:
        return None
    g=json.loads(row['collection'])
    if not g['starts']<=t<g['expires'] or row['accepted']>=g['quota']:return None
    return g

def revoke(c,key,r,signature,t):
    check(key,'revocation-v1',r,signature)
    exact(r,('page','scope'))
    pid=ident(r['page'])
    if r['scope']=='publication':
        c.execute('INSERT OR IGNORE INTO channel_revoked_pages VALUES(?,?)',(pid,t))
        row=c.execute('SELECT * FROM channel_pages WHERE id=?',(pid,)).fetchone()
        if not row:return pid
        c.execute('UPDATE channel_pages SET revoked=COALESCE(revoked,?),collection_revoked=COALESCE(collection_revoked,?) WHERE id=?',(t,t,row['id']))
    elif r['scope']=='collection':
        row=_row(c,pid)
        c.execute('UPDATE channel_pages SET collection_revoked=COALESCE(collection_revoked,?) WHERE id=?',(t,row['id']))
    else:raise ValueError('Unknown scope')
    return row['id']

def page(c,page_id,t):
    row=_row(c,page_id)
    if not _active(row,t):raise ValueError('Page unavailable')
    m=json.loads(row['manifest'])
    return {'id':page_id,'mode':'test','title':m['title'],'description':m['description'],
            'limitations':m['limitations'],'price_cents':m['price_cents'],
            'collection_open':bool(_collection(row,t)),'notice':NOTICE_VERSION}

def inspect(c,key,page_id,nonce,t):
    """Authenticated state proof; nonce prevents reuse of a previous response."""
    ident(page_id);ident(nonce)
    row=c.execute('SELECT * FROM channel_pages WHERE id=?',(page_id,)).fetchone()
    tombstone=bool(c.execute('SELECT 1 FROM channel_revoked_pages WHERE id=?',(page_id,)).fetchone())
    payload={'page':page_id,'nonce':nonce,'mode':'test','at':t,'exists':bool(row),
             'publication_hash':hashlib.sha256(row['manifest'].encode()).hexdigest() if row else None,
             'collection_hash':hashlib.sha256(row['collection'].encode()).hexdigest() if row and row['collection'] else None,
             'publication_revoked':tombstone or bool(row and row['revoked'] is not None),
             'collection_revoked':tombstone or bool(row and row['collection_revoked'] is not None),
             'publication_open':bool(row and _active(row,t)),
             'collection_open':bool(row and _collection(row,t))}
    return {'payload':payload,'signature':sign(key,'status-v1',payload)}

def participant_token(key,page_id,nonce=None):
    ident(page_id)
    nonce=secrets.token_hex(16) if nonce is None else ident(nonce)
    return nonce+'.'+sign(key,'participant-v1',{'page':page_id,'nonce':nonce})

def _participant(key,page_id,token):
    if not isinstance(token,str) or len(token)!=97:raise ValueError('Invalid participant token')
    nonce,signature=token.split('.',1)
    ident(nonce)
    check(key,'participant-v1',{'page':page_id,'nonce':nonce},signature)
    return sign(key,'participant-storage-v1',{'page':page_id,'nonce':nonce})

def record(c,key,page_id,token,b,t):
    """Caller must hold a BEGIN IMMEDIATE transaction for quota/deduplication."""
    exact(b,('kind','segment','consent','notice'))
    row=_row(c,page_id)
    if not _collection(row,t):raise ValueError('Collection unavailable')
    if b['consent'] is not True or b['notice']!=NOTICE_VERSION:
        raise ValueError('Explicit consent required')
    if b['kind'] not in KINDS or type(b['segment']) is not bool:
        raise ValueError('Invalid signal')
    participant=_participant(key,page_id,token)
    if c.execute('SELECT 1 FROM channel_tombstones WHERE page=? AND participant=?',(page_id,participant)).fetchone():
        raise ValueError('Participant already counted')
    event=secrets.token_hex(16);delete_token=secrets.token_hex(32)
    c.execute('INSERT INTO channel_signals VALUES(?,?,?,?,?,?,?,?)',
              (event,page_id,participant,b['kind'],int(b['segment']),t,NOTICE_VERSION,hashlib.sha256(delete_token.encode()).hexdigest()))
    c.execute('INSERT INTO channel_tombstones VALUES(?,?,?)',(page_id,participant,row['expires']))
    c.execute('UPDATE channel_pages SET accepted=accepted+1 WHERE id=?',(page_id,))
    return {'id':event,'delete_token':delete_token,'mode':'test','paid_order':False}

def withdraw(c,event,token):
    ident(event);ident(token,HEX)
    hashed=hashlib.sha256(token.encode()).hexdigest()
    row=c.execute('SELECT delete_hash FROM channel_signals WHERE id=?',(event,)).fetchone()
    if not row or not hmac.compare_digest(row['delete_hash'],hashed):return False
    c.execute('DELETE FROM channel_signals WHERE id=?',(event,))
    return True

def purge(c,t):
    c.execute('DELETE FROM channel_signals WHERE observed<=?',(t-RETENTION,))
    c.execute('DELETE FROM channel_tombstones WHERE expires<=?',(t,))

def export(c,key,page_id,t):
    """Admin-only transport payload, no raw participant token or delete secret."""
    row=_row(c,page_id);purge(c,t)
    items=[{'id':x['id'],'participant':x['participant'],'kind':x['kind'],
            'segment':bool(x['segment']),'observed':x['observed'],'notice':x['notice']}
           for x in c.execute('SELECT * FROM channel_signals WHERE page=? ORDER BY observed,id',(page_id,))]
    payload={'page':page_id,'snapshot':row['snapshot'],'mode':'test','exported':t,
             'accepted_total':row['accepted'],'signals':items,'paid_orders':0}
    return {'payload':payload,'signature':sign(key,'export-v1',payload)}

def connect(path):
    c=sqlite3.connect(path,timeout=10,isolation_level=None)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
