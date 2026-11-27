"""Deterministic internal HERMES preparation. No paid calls, external actions or customer data."""
import json

import acquisition as ac
import business as b
import commercial
import laboratory as lab
from departments import product_demonstrations, marketing_coordination

LIMIT='Préparation HERMES interne. Aucun lancement, aucune demande réelle, aucune preuve nouvelle de performance.'
MAX_PER_CYCLE=3

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS hermes_preparations(
        draft INTEGER PRIMARY KEY REFERENCES acquisition_drafts(id),
        payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created INTEGER NOT NULL);""")

def _demo(c,payload):
    return product_demonstrations.demo(c,payload,lab=lab,json=json)

def prepare(c,did,t):
    row=ac._row(c,did)
    if ac.state(c,row)!='draft':raise ValueError('Brouillon périmé')
    old=c.execute('SELECT 1 FROM hermes_preparations WHERE draft=?',(did,)).fetchone()
    if old:return did
    p=ac.preview(c,did)
    v=ac._offer(c,row['offer'])
    plan=v['plan']
    packet={'classification':'internal_hermes_packet','draft':did,'offer':row['offer'],
            'snapshot_sha256':row['snapshot_sha256'],'artifact_sha256':p['artifact_sha256'],
            'language':'fr','title':p['title'],'offer_text':p['offer'],'deliverables':p['deliverables'],
            'audience_hypothesis':plan['audience'],'price_cents':p['price_cents'],
            'limitations':p['limitations'],'risks':p['risks'],
            'faq':[{'question':'Le prix est-il définitif ?', 'answer':'Non, prix indicatif non validé.'},
                   {'question':'Puis-je commander ?', 'answer':'Non, aucune vente autorisée.'},
                   {'question':'La performance réelle est-elle garantie ?', 'answer':'Non, preuves techniques limitées aux cas testés.'}],
            'product_demo':_demo(c,p),
            'next_action':'review_public_content_before_any_activation','limit':LIMIT}
    c.execute('INSERT INTO hermes_preparations VALUES(?,?,?,?)',(did,b.canonical(packet),b.digest(packet),t))
    return did

def packet(c,did):
    row=ac._row(c,did)
    if ac.state(c,row)!='draft':raise ValueError('Brouillon périmé')
    record=c.execute('SELECT * FROM hermes_preparations WHERE draft=?',(did,)).fetchone()
    if not record:raise ValueError('Dossier HERMES absent')
    p=json.loads(record['payload'])
    if b.digest(p)!=record['payload_sha256']:raise ValueError('Dossier HERMES modifié')
    if p['product_demo']['status']=='historical_evidence' and _demo(c,p | {'offer_id':p['offer']})!=p['product_demo']:
        raise ValueError('Preuve historique modifiée ou remplacée')
    return p

def run_once(c,t=None):
    return marketing_coordination.acquisition_cycle(c,t,b=b,commercial=commercial,ac=ac,prepare=prepare,max_per_cycle=MAX_PER_CYCLE)

def status(c,project=None):
    rows=c.execute("""SELECT h.*,d.offer,d.snapshot_sha256,o.project FROM hermes_preparations h
        JOIN acquisition_drafts d ON d.id=h.draft JOIN commercial_offers o ON o.id=d.offer
        WHERE (? IS NULL OR o.project=?) ORDER BY h.draft DESC""",(project,project))
    out=[]
    for row in rows:
        try:
            p=packet(c,row['draft'])
            out.append({'draft':row['draft'],'offer':row['offer'],'project':row['project'],
                        'snapshot_sha256':row['snapshot_sha256'],'created':row['created'],
                        'demo_status':p['product_demo']['status'],'state':'internal_ready'})
        except (ValueError,KeyError,TypeError,AttributeError):
            out.append({'draft':row['draft'],'offer':row['offer'],'project':row['project'],'state':'unavailable'})
    return {'packets':out,'real_prospects':0,'external_authorized':False,'limit':LIMIT}

def agent_context(c,mid,agent):
    return marketing_coordination.acquisition_context(c,mid,agent,commercial=commercial,json=json,status=status)
