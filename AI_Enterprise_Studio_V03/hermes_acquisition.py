"""Deterministic internal HERMES preparation. No paid calls, external actions or customer data."""
import json

import acquisition as ac
import business as b
import commercial
import laboratory as lab

LIMIT='Préparation HERMES interne. Aucun lancement, aucune demande réelle, aucune preuve nouvelle de performance.'
MAX_PER_CYCLE=3

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS hermes_preparations(
        draft INTEGER PRIMARY KEY REFERENCES acquisition_drafts(id),
        payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created INTEGER NOT NULL);""")

def _demo(c,payload):
    """Use the canonical existing synthetic benchmark, never execute an artifact here."""
    row=c.execute('SELECT a.* FROM artifacts a JOIN missions m ON m.id=a.mission WHERE a.id=(SELECT artifact FROM commercial_offers WHERE id=?) AND m.state=\'terminée\' AND a.agent=\'NEXUS\'',(payload['offer_id'],)).fetchone()
    base={'classification':'synthetic_product_demo','artifact_sha256':payload['artifact_sha256'],
          'status':'unavailable','reason':'Aucun benchmark compatible exact; ne pas inventer une démonstration.',
          'new_execution':False}
    if not row or lab.digest(row['content'])!=payload['artifact_sha256'] or not lab.supports(row):return base
    proof=lab.canonical(c,row)
    if not proof or proof['status']!='passed':return base
    run=c.execute('SELECT result FROM laboratory_runs WHERE id=?',(proof['id'],)).fetchone()
    result=json.loads(run['result'])
    fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
    if result.get('fixture_sha256')!=lab.digest(lab.encode(fixtures)) or result.get('sha256')!=payload['artifact_sha256']:
        return base
    case=next((x for x in result.get('cases',[]) if x.get('name')=='anomalies' and x.get('status')=='passed'),None)
    if not case or not isinstance(case.get('output'),str):return base
    return {**base,'status':'historical_evidence','reason':'Extrait du résultat historique sur données synthétiques; pas de nouvelle exécution.',
            'laboratory_run':proof['id'],'profile':lab.PROFILE,'size':300,'seed':lab.DEFAULT_SEED,
            'input_json':fixtures[1]['input'],'observed_output':case['output'],
            'metrics':proof['metrics'],'limit':lab.LIMIT}

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
    """Create at most three internal packets per cycle. Never override a revoked draft."""
    t=b.now() if t is None else t
    made=[]
    for project in c.execute("SELECT id FROM projects WHERE state='active' ORDER BY id"):
        if len(made)>=MAX_PER_CYCLE:break
        v=commercial.project_status(c,project['id'])['offer']
        if not v:continue
        try:
            _,eligible,_=b.gate(c,b.offer_row(c,v['id']))
            if not eligible:continue
            snap=b.digest(b.frozen(v))
            row=c.execute('SELECT * FROM acquisition_drafts WHERE offer=? AND snapshot_sha256=? AND language=\'fr\'',(v['id'],snap)).fetchone()
            if row and ac.state(c,row)!='draft':continue
            if row and c.execute('SELECT 1 FROM hermes_preparations WHERE draft=?',(row['id'],)).fetchone():continue
            did=ac.prepare(c,{'confirm':True,'offer':v['id'],'snapshot_sha256':snap,'language':'fr'},t)
            prepare(c,did,t)
            made.append(did)
        except (ValueError,KeyError,TypeError,AttributeError):
            continue
    return made

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
    """Only a project-scoped compact view for HERMES in an explicitly scoped commercial campaign."""
    if agent!='HERMES':return None
    scope=commercial.scope(c,mid)
    if not scope or scope['state']!='actif' or scope['mission_state']!='en cours' or scope['mode']!='cloud' or scope['project_state']!='active':
        return None
    if not json.loads(scope['permissions']).get('market'):return None
    out=status(c,scope['project'])
    out['packets']=[p for p in out['packets'] if p['state']=='internal_ready'][:3]
    return out
