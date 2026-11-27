"""HERMES internal multi-channel marketing drafts, versioned and fail closed."""
import json
import business as b
import hermes_acquisition as h
import marketing_review as sentinel
import marketing_templates as templates
import commercial
from departments import marketing_coordination

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS marketing_drafts(
        draft INTEGER NOT NULL REFERENCES acquisition_drafts(id), revision INTEGER NOT NULL,
        payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL, review TEXT NOT NULL,
        created INTEGER NOT NULL, PRIMARY KEY(draft,revision));""")

def prepare(c,did,t):
    h.packet(c,did)
    facts=sentinel.evidence(c,did)
    payload={'classification':'internal_marketing_draft','revision':templates.REVISION,
             'language':'fr','facts':facts,
             'content':templates.render(facts['price_cents'],facts['size'],facts['tp'],facts['fp'],facts['fn']),
             'limit':templates.LIMIT}
    review=sentinel.review(c,did,payload)
    if review['state']!='technical_pass':raise ValueError('Contrôle marketing refusé')
    c.execute('INSERT OR IGNORE INTO marketing_drafts VALUES(?,?,?,?,?,?)',
              (did,templates.REVISION,b.canonical(payload),b.digest(payload),b.canonical(review),t))
    return packet(c,did)

def packet(c,did):
    h.packet(c,did)
    row=c.execute('SELECT * FROM marketing_drafts WHERE draft=? AND revision=?',(did,templates.REVISION)).fetchone()
    if not row:raise ValueError('Dossier marketing absent')
    p=json.loads(row['payload'])
    review=sentinel.review(c,did,p)
    if b.digest(p)!=row['payload_sha256'] or review['state']!='technical_pass' or b.canonical(review)!=row['review']:
        raise ValueError('Dossier marketing ou preuve périmé')
    return {'payload':p,'review':review}

def run_once(c,t=None):
    return marketing_coordination.content_cycle(c,t,b=b,templates=templates,prepare=prepare)

def status(c,project=None):
    out=[]
    for row in c.execute("""SELECT h.draft,d.offer,o.project FROM hermes_preparations h
        JOIN acquisition_drafts d ON d.id=h.draft JOIN commercial_offers o ON o.id=d.offer
        WHERE (? IS NULL OR o.project=?) ORDER BY h.draft DESC""",(project,project)):
        try:
            packet(c,row['draft'])
            state='technical_pass'
        except (ValueError,TypeError,KeyError,AttributeError,RuntimeError,IndexError):
            state='unavailable'
        out.append({**dict(row),'state':state,'publication_authorized':False})
    return {'drafts':out,'publication_authorized':False,'video_generated':False,'limit':sentinel.LIMIT}

def agent_context(c,mid,agent):
    return marketing_coordination.content_context(c,mid,agent,commercial=commercial,json=json,status=status)
