"""Persistent activity portfolio. Facts and local costs, never inferred commercial validation."""
import hashlib,json
import laboratory
import improvement
from departments import accounting, portfolio_progression

STATES=('active','paused','archived')
def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY, origin TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
        opportunity INTEGER, state TEXT NOT NULL DEFAULT 'active', created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS project_missions(
        mission INTEGER PRIMARY KEY REFERENCES missions(id), project INTEGER NOT NULL REFERENCES projects(id),
        provenance TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS project_missions_project ON project_missions(project);
        CREATE TABLE IF NOT EXISTS campaign_projects(
        campaign INTEGER PRIMARY KEY REFERENCES campaigns(id), project INTEGER REFERENCES projects(id),
        scope TEXT NOT NULL);""")
    sync(c)

def _get(c,origin,title,opp=None):
    c.execute('INSERT OR IGNORE INTO projects(origin,title,opportunity) VALUES(?,?,?)',(origin,title[:160],opp))
    return c.execute('SELECT id FROM projects WHERE origin=?',(origin,)).fetchone()[0]

def attach(c,mid,pid,reason):
    if not c.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone() or not c.execute("SELECT 1 FROM missions WHERE id=? AND mode='cloud'",(mid,)).fetchone():raise ValueError('Lien de projet invalide')
    old=c.execute('SELECT project FROM project_missions WHERE mission=?',(mid,)).fetchone()
    if old and old[0]!=pid:raise ValueError('Mission déjà attribuée à une autre activité')
    c.execute('INSERT OR IGNORE INTO project_missions(mission,project,provenance) VALUES(?,?,?)',(mid,pid,reason))

def sync(c):
    """Idempotent, only explicit lineage or an unambiguous source mission. No text matching."""
    for m in c.execute("SELECT id,title FROM missions WHERE mode='cloud' AND state='terminée' ORDER BY id").fetchall():
        mid=m['id']
        opps=c.execute('SELECT id,title FROM opportunities WHERE mission=? ORDER BY id',(mid,)).fetchall()
        for o in opps:_get(c,'opportunity:'+str(o['id']),o['title'],o['id'])
        if c.execute('SELECT 1 FROM project_missions WHERE mission=?',(mid,)).fetchone():continue
        parent=c.execute("""SELECT pm.project FROM mission_artifact_refs r JOIN artifacts a ON a.id=r.artifact
            JOIN project_missions pm ON pm.mission=a.mission WHERE r.mission=?""",(mid,)).fetchone()
        if parent:
            attach(c,mid,parent[0],'référence exacte');continue
        artifact=c.execute("SELECT id,name FROM artifacts WHERE mission=? AND agent='NEXUS' ORDER BY id LIMIT 1",(mid,)).fetchone()
        if artifact:
            # Multiple distinct opportunities are not silently merged into a product.
            pid=_get(c,'artifact-mission:'+str(mid),artifact['name'])
            attach(c,mid,pid,'production historique');continue
        if len(opps)==1:
            pid=_get(c,'opportunity:'+str(opps[0]['id']),opps[0]['title'],opps[0]['id'])
            attach(c,mid,pid,'opportunité unique')
        # A mixed exploration remains unallocated, rather than charging several activities.

def project(c,pid):
    return c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()

def scope(c,cid):
    return c.execute('SELECT * FROM campaign_projects WHERE campaign=?',(cid,)).fetchone()

def latest(c,pid):
    ref=improvement.pinned(c,pid)
    if ref:return ref
    row=c.execute("""SELECT a.* FROM artifacts a JOIN project_missions pm ON pm.mission=a.mission
        JOIN missions m ON m.id=a.mission WHERE pm.project=? AND m.state='terminée'
        AND a.agent='NEXUS' ORDER BY a.mission DESC, CASE WHEN lower(a.name) LIKE '%.html' THEN 0 ELSE 1 END,a.id DESC LIMIT 1""",(pid,)).fetchone()
    if row:return row
    # Older schema can call sync before draft recovery migration.
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='draft_recoveries'").fetchone():
        import draft_recovery
        return draft_recovery.adopted(c,pid)
    return None

def evidence(c,a):
    out=[]
    if not a:return out
    sha=hashlib.sha256(a['content'].encode('utf8')).hexdigest()
    for v in c.execute('SELECT id,mission,agent,result FROM verification_results WHERE artifact=? ORDER BY id',(a['id'],)):
        try:
            r=json.loads(v['result'])
            if r.get('sha256')!=sha:continue
            checks=r.get('checks',[])
            state=r.get('status')
            if state=='passed' and (not checks or not all(x.get('passed') is True for x in checks)):state='invalid'
            out.append({'id':v['id'],'mission':v['mission'],'agent':v['agent'],'status':state,'cases':len(checks)})
        except (ValueError,TypeError,AttributeError):continue
    return out

def history(c,pid,kind,aid=None):
    return c.execute("""SELECT m.id,m.state FROM project_missions pm JOIN missions m ON m.id=pm.mission
        JOIN campaign_missions cm ON cm.mission=m.id WHERE pm.project=? AND cm.kind=?
        AND (? IS NULL OR cm.artifact=?) ORDER BY m.id""",(pid,kind,aid,aid)).fetchall()

def economic_hold(c,oid):
    """Only an exact, latest completed Cloud assessment with independently recalculated values."""
    if oid is None:return False
    import intelligence as intel
    import collective_evidence as ce
    row=c.execute("""SELECT o.*,a.id AS assessment_id,a.agent AS assessment_agent,a.assumptions,
        a.source_runs,a.result,a.opportunity_sha256 FROM opportunities o JOIN market_assessments a ON a.opportunity=o.id
        JOIN missions m ON m.id=a.mission WHERE o.id=? AND a.mission=o.mission AND m.mode='cloud'
        AND m.state='terminée' AND a.id=(SELECT MAX(b.id) FROM market_assessments b WHERE b.opportunity=o.id)""",(oid,)).fetchone()
    if not row:return False
    try:return ce.assessment(c,row)['result']['scenario_viable'] is False
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):return False

def next_step(c,pid,flags):
    return portfolio_progression.next_step(c,pid,flags,project=project,latest=latest,economic_hold=economic_hold,history=history,evidence=evidence,laboratory=laboratory)

def recommend(c,flags):
    return portfolio_progression.recommend(c,flags,next_step=next_step)

def select(c,requested,flags):
    return portfolio_progression.select(c,requested,flags,recommend=recommend,project=project,next_step=next_step)

def set_state(c,pid,state):
    if type(pid) is not int or not 1<=pid<=9007199254740991 or state not in STATES or not project(c,pid):raise ValueError('Activité ou état invalide')
    if c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone() or c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone():raise ValueError('Arrêter le travail actif avant de modifier le portefeuille')
    c.execute('UPDATE projects SET state=? WHERE id=?',(state,pid))

def status(c):
    flags=dict.fromkeys(('research','production','tests','market'),True)
    items=[]
    for p in c.execute('SELECT * FROM projects ORDER BY id'):
        pid=p['id'];a=latest(c,pid)
        o=c.execute('SELECT id,title,body,next_test FROM opportunities WHERE id=?',(p['opportunity'],)).fetchone() if p['opportunity'] is not None else None
        ms=[dict(r) for r in c.execute("""SELECT m.id,m.title,m.state,pm.provenance FROM project_missions pm
            JOIN missions m ON m.id=pm.mission WHERE pm.project=? ORDER BY m.id DESC""",(pid,))]
        spend=accounting.project_total(c,pid)
        files=[dict(r) for r in c.execute("""SELECT a.id,a.name,a.version,a.agent FROM artifacts a
            JOIN project_missions pm ON pm.mission=a.mission WHERE pm.project=? ORDER BY a.id DESC""",(pid,))]
        search_count=c.execute("""SELECT COUNT(*) FROM searches s JOIN project_missions pm ON pm.mission=s.mission WHERE pm.project=? AND s.status='reçue'""",(pid,)).fetchone()[0]
        market=sum(r['state']=='terminée' for r in history(c,pid,'market'))
        step,reason=next_step(c,pid,flags)
        items.append({**dict(p),'opportunity_data':dict(o) if o else None,'missions':ms,'files':files,
            'latest_artifact':a['id'] if a else None,'versions':improvement.status(c,pid),'improvement_modes':improvement.available(c,a),'proofs':evidence(c,a),'laboratory':laboratory.canonical(c,a),'spent':spend,'search_results':search_count,
            'market_studies':market,'next_kind':step[0] if step else None,'reason':reason})
    unallocated=accounting.unallocated_total(c)
    return {'projects':items,'unallocated':unallocated,'recommendation':recommend(c,flags),
        'limit':'Coûts locaux attribués une seule fois par mission; études et preuves bornées, aucune demande ou rentabilité certifiée.'}
