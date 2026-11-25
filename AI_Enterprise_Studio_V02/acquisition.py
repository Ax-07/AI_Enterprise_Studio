"""Acquisition staging: immutable offer-bound drafts, never public or collecting.
No provider calls, agent authority, trial creation, or customer data.
"""
import html
import json
import business

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
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError('Texte de préparation invalide')
    return value.strip()

def _page(payload):
    e = lambda v: html.escape(str(v), quote=True)
    price = payload['price_cents']
    return ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; form-action \'none\'; base-uri \'none\'">'
        '<title>Brouillon commercial</title><style>'
        'body{font:17px system-ui,sans-serif;max-width:800px;margin:40px auto;padding:20px;color:#183040}'
        'header{background:#eef2f5;padding:16px;border-radius:8px}section{margin:24px 0}'
        'button{padding:10px}p{white-space:pre-wrap;overflow-wrap:anywhere}</style></head>'
        '<body><header><strong>APERÇU INTERNE — NON PUBLIÉ</strong>'
        '<p>Aucun achat, contact ou enregistrement de données possible.</p></header>'
        '<main><h1>'+e(payload['title'])+'</h1><section><h2>Proposition à valider</h2><p>'
        +e(payload['offer'])+'</p><h2>Livrables envisagés</h2><p>'
        +e(payload['deliverables'])+'</p><h2>Prix indicatif non validé</h2><p>'
        +e(f'{price//100},{price%100:02d} EUR')+'</p><h2>Limites</h2><p>'
        +e(payload['limitations'])+'</p></section><section><h2>Parcours fictif</h2>'
        '<p>Exemple illustratif : un visiteur manifeste son intérêt ou demande une démonstration. '
        'Ces actions ne constituent ni commande ni preuve de demande.</p>'
        '<button disabled>Je suis intéressé</button> <button disabled>Demander une démonstration</button>'
        '</section></main></body></html>')

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
               'language':'fr','classification':'internal_draft','offer_id':v['id'],
               'artifact_sha256':v['artifact_sha256'],'snapshot_sha256':snap}
    payload['html'] = _page(payload)
    old = c.execute('SELECT id,revoked FROM acquisition_drafts WHERE offer=? AND snapshot_sha256=? AND language=?',
                    (v['id'],snap,'fr')).fetchone()
    if old:
        if old['revoked'] is not None:
            raise ValueError('Brouillon révoqué; historique conservé')
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
        if (business.digest(payload)!=row['payload_sha256'] or
            business.digest(business.frozen(v))!=row['snapshot_sha256']):
            return 'reference_changed'
    except (ValueError,TypeError,KeyError,AttributeError):
        return 'reference_changed'
    return 'draft'

def preview(c, did):
    row=_row(c,did)
    if state(c,row)!='draft':
        raise ValueError('Brouillon révoqué ou référence modifiée')
    return json.loads(row['payload'])['html']

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
