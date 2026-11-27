"""Acquisition staging: immutable offer-bound drafts, never public or collecting.
No provider calls, agent authority, trial creation, or customer data.
"""
import html
import json
import business
from departments import acquisition_preview

LIMIT = ('Brouillons locaux uniquement. Aucun canal public, formulaire actif, '
         'prospect, commande, paiement, dépense ou période d’observation déclenchés.')

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS acquisition_drafts(
        id INTEGER PRIMARY KEY,
        offer INTEGER NOT NULL REFERENCES commercial_offers(id),
        snapshot_sha256 TEXT NOT NULL,
        language TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        created INTEGER NOT NULL,
        revoked INTEGER,
        UNIQUE(offer,snapshot_sha256,language));
        CREATE TABLE IF NOT EXISTS acquisition_events(
        id INTEGER PRIMARY KEY,
        draft INTEGER NOT NULL REFERENCES acquisition_drafts(id),
        event TEXT NOT NULL,
        at INTEGER NOT NULL);""")

def _offer(c, oid):
    row = business.offer_row(c, oid)
    v, eligible, _ = business.gate(c, row)
    if not eligible:
        raise ValueError('Offre non admissible à une préparation d’acquisition')
    return v

def _text(value, limit=12000):
    return acquisition_preview.text(value,limit)

def demo(payload):
    return acquisition_preview.demo(payload)

def _page(payload):
    return acquisition_preview.page(payload,html=html)

def prepare(c, b, t=None):
    t = business.now() if t is None else t
    business.fields(b, ('offer','snapshot_sha256','language'))
    v = _offer(c, b['offer'])
    snap = business.digest(business.frozen(v))
    if b['snapshot_sha256'] != snap:
        raise ValueError('Offre modifiée; actualiser')
    # Do not mislabel French source text as a translated public page.
    if b['language'] != 'fr':
        raise ValueError('Traduction vérifiée indisponible; aperçu français uniquement')
    p = v['plan']
    project = c.execute('SELECT title FROM projects WHERE id=?',(v['project'],)).fetchone()
    payload = {'title':_text(project['title'],1000),
               'offer':_text(p['offer']), 'deliverables':_text(p['deliverables']),
               'price_cents':business.integer(p['price_cents'],1,100000000),
               'limitations':'Prototype ou prestation en préparation. Demande, prix et performances sur données réelles non validés. Aucune garantie ni vente autorisée.',
               'risks':_text(p['risks']), 'language':'fr','classification':'internal_draft','offer_id':v['id'],
               'artifact_sha256':v['artifact_sha256'],'snapshot_sha256':snap}
    payload['demo'] = demo(payload)
    payload['html'] = _page(payload)
    old = c.execute('SELECT id,revoked FROM acquisition_drafts WHERE offer=? AND snapshot_sha256=? AND language=?',
                    (v['id'],snap,'fr')).fetchone()
    if old:
        if state(c,_row(c,old['id']))!='draft':
            raise ValueError('Brouillon révoqué ou référence modifiée; historique conservé')
        return old['id']
    did = c.execute("""INSERT INTO acquisition_drafts(offer,snapshot_sha256,language,payload,payload_sha256,created)
                    VALUES(?,?,?,?,?,?)""",(v['id'],snap,'fr',business.canonical(payload),business.digest(payload),t)).lastrowid
    c.execute("INSERT INTO acquisition_events(draft,event,at) VALUES(?,'prepared',?)",(did,t))
    return did

def _row(c, did):
    row = c.execute('SELECT * FROM acquisition_drafts WHERE id=?',(business.integer(did),)).fetchone()
    if not row:
        raise ValueError('Brouillon absent')
    return row

def state(c, row):
    if row['revoked'] is not None:
        return 'revoked'
    try:
        payload=json.loads(row['payload'])
        v=_offer(c,row['offer'])
        project=c.execute('SELECT title FROM projects WHERE id=?',(v['project'],)).fetchone()
        if (payload['title']!=_text(project['title'],1000) or
            business.digest(payload)!=row['payload_sha256'] or
            business.digest(business.frozen(v))!=row['snapshot_sha256']):
            return 'reference_changed'
    except (ValueError,TypeError,KeyError,AttributeError):
        return 'reference_changed'
    return 'draft'

def preview(c, did):
    row=_row(c,did)
    if state(c,row)!='draft':
        raise ValueError('Brouillon révoqué ou référence modifiée')
    return json.loads(row['payload'])

def revoke(c,b,t=None):
    t=business.now() if t is None else t
    business.fields(b,('draft',))
    row=_row(c,b['draft'])
    if row['revoked'] is not None:
        raise ValueError('Brouillon déjà révoqué')
    c.execute('UPDATE acquisition_drafts SET revoked=? WHERE id=?',(t,row['id']))
    c.execute("INSERT INTO acquisition_events(draft,event,at) VALUES(?,'revoked',?)",(row['id'],t))
    return row['id']

def status(c):
    drafts=[]
    for row in c.execute('SELECT * FROM acquisition_drafts ORDER BY id DESC'):
        drafts.append({k:row[k] for k in ('id','offer','snapshot_sha256','language','payload_sha256','created','revoked')})
        drafts[-1]['state']=state(c,row)
    return {'drafts':drafts,'events':[dict(x) for x in c.execute('SELECT * FROM acquisition_events ORDER BY id DESC')],
            'publication_authorized':False,'collection_authorized':False,'channel_ready':False,
            'external_spend_cents':0,'prospects':0,'limit':LIMIT}
