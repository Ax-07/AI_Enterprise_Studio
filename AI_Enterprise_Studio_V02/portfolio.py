"""Persistent activity portfolio. Facts and local costs, never inferred commercial validation."""
import hashlib,json
import laboratory

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
    return c.execute("""SELECT a.* FROM artifacts a JOIN project_missions pm ON pm.mission=a.mission
        JOIN missions m ON m.id=a.mission WHERE pm.project=? AND m.state='terminée'
        AND a.agent='NEXUS' ORDER BY a.mission DESC, CASE WHEN lower(a.name) LIKE '%.html' THEN 0 ELSE 1 END,a.id DESC LIMIT 1""",(pid,)).fetchone()

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

def next_step(c,pid,flags):
    p=project(c,pid)
    if not p or p['state']!='active':return None,'Activité suspendue ou archivée.'
    a=latest(c,pid)
    if not a:
        if flags['production'] and p['opportunity'] is not None and not history(c,pid,'create'):
            o=c.execute('SELECT id,title,next_test FROM opportunities WHERE id=?',(p['opportunity'],)).fetchone()
            if o:return ('create',None,dict(o)),'Premier prototype et expérience interne.'
        return None,'Aucun livrable exploitable; production non autorisée ou déjà tentée.'
    aid=a['id'];proofs=evidence(c,a)
    if laboratory.supports(a):
        lab=laboratory.canonical(c,a)
        if not lab or lab['status']=='unavailable':
            if flags['tests']:return ('laboratory',aid,None),'Banc d’essai indépendant de 300 lignes, sans appel IA.'
            return None,'Banc d’essai requis mais non autorisé.'
        if lab['status']!='passed':return None,'Banc d’essai non réussi; diagnostic et correction ciblée nécessaires.'
    independent=[v for v in proofs if v['agent']=='SENTINEL']
    if any(v['status']=='failed' for v in independent):
        if flags['production'] and not history(c,pid,'improve',aid):
            return ('improve',aid,None),'Échec fonctionnel observé sur cette version.'
        return None,'Échec indépendant non résolu; examen requis.'
    if not any(v['status']=='passed' for v in independent):
        if flags['tests'] and a['name'].lower().endswith(('.html','.csv','.json')) and not history(c,pid,'functional',aid):
            return ('functional',aid,None),'Aucune preuve indépendante réussie sur cette version.'
        return None,'Audit indépendant manquant ou déjà tenté; examen requis.'
    if flags['market'] and not history(c,pid,'market',aid):
        return ('market',aid,None),'Étude commerciale interne, sans validation de demande.'
    return None,'Étapes internes déjà étudiées ou non autorisées; preuves commerciales encore à établir.'

def recommend(c,flags):
    # Prioritize a concrete next step; least recently studied first. No invented score.
    candidates=[]
    for p in c.execute("SELECT * FROM projects WHERE state='active' ORDER BY id"):
        step,reason=next_step(c,p['id'],flags)
        if step:
            last=c.execute('SELECT COALESCE(MAX(mission),0) FROM project_missions WHERE project=?',(p['id'],)).fetchone()[0]
            candidates.append((last,p['id'],step,reason))
    if not candidates:return None
    _,pid,step,reason=min(candidates,key=lambda x:(x[0],x[1]))
    return {'id':pid,'kind':step[0],'reason':reason}

def select(c,requested,flags):
    if requested=='explore':
        if not flags['research']:raise ValueError('Exploration non autorisée')
        return None,'explore'
    if requested=='auto':
        rec=recommend(c,flags)
        if rec:return rec['id'],'project'
        if flags['research']:return None,'explore'
        raise ValueError('Aucune activité avec une prochaine étape autorisée')
    if type(requested) is not int or not 1<=requested<=9007199254740991:raise ValueError('Activité invalide')
    p=project(c,requested)
    if not p or p['state']!='active':raise ValueError('Activité inactive ou inconnue')
    if not next_step(c,requested,flags)[0]:raise ValueError('Aucune prochaine étape autorisée pour cette activité')
    return requested,'project'

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
        spend=c.execute("""SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved)),0) FROM ledger l
            JOIN project_missions pm ON pm.mission=l.mission WHERE pm.project=?""",(pid,)).fetchone()[0]
        files=[dict(r) for r in c.execute("""SELECT a.id,a.name,a.version,a.agent FROM artifacts a
            JOIN project_missions pm ON pm.mission=a.mission WHERE pm.project=? ORDER BY a.id DESC""",(pid,))]
        search_count=c.execute("""SELECT COUNT(*) FROM searches s JOIN project_missions pm ON pm.mission=s.mission WHERE pm.project=? AND s.status='reçue'""",(pid,)).fetchone()[0]
        market=sum(r['state']=='terminée' for r in history(c,pid,'market'))
        step,reason=next_step(c,pid,flags)
        items.append({**dict(p),'opportunity_data':dict(o) if o else None,'missions':ms,'files':files,
            'latest_artifact':a['id'] if a else None,'proofs':evidence(c,a),'laboratory':laboratory.canonical(c,a),'spent':spend,'search_results':search_count,
            'market_studies':market,'next_kind':step[0] if step else None,'reason':reason})
    unallocated=c.execute("""SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved)),0) FROM ledger l
        LEFT JOIN project_missions pm ON pm.mission=l.mission WHERE pm.mission IS NULL""").fetchone()[0]
    return {'projects':items,'unallocated':unallocated,'recommendation':recommend(c,flags),
        'limit':'Coûts locaux attribués une seule fois par mission; études et preuves bornées, aucune demande ou rentabilité certifiée.'}
