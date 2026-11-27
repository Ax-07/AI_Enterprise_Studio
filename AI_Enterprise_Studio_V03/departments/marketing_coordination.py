"""Bounded local marketing cycles and project-scoped agent context.
Persistence and authorization remain in the historical callbacks.
"""

def acquisition_cycle(c,t=None,*,b,commercial,ac,prepare,max_per_cycle):
    """Create at most three internal packets per cycle. Never override a revoked draft."""
    t=b.now() if t is None else t
    made=[]
    for project in c.execute("SELECT id FROM projects WHERE state='active' ORDER BY id"):
        if len(made)>=max_per_cycle:break
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


def acquisition_context(c,mid,agent,*,commercial,json,status):
    """Only a project-scoped compact view for HERMES in an explicitly scoped commercial campaign."""
    if agent!='HERMES':return None
    scope=commercial.scope(c,mid)
    if not scope or scope['state']!='actif' or scope['mission_state']!='en cours' or scope['mode']!='cloud' or scope['project_state']!='active':
        return None
    if not json.loads(scope['permissions']).get('market'):return None
    out=status(c,scope['project'])
    out['packets']=[p for p in out['packets'] if p['state']=='internal_ready'][:3]
    return out


def content_cycle(c,t=None,*,b,templates,prepare):
    t=b.now() if t is None else t
    made=[]
    for row in c.execute("""SELECT h.draft FROM hermes_preparations h LEFT JOIN marketing_drafts m
        ON m.draft=h.draft AND m.revision=? WHERE m.draft IS NULL ORDER BY h.draft""",(templates.REVISION,)).fetchall():
        if len(made)>=3:break
        try:prepare(c,row['draft'],t);made.append(row['draft'])
        except (ValueError,TypeError,KeyError,AttributeError,RuntimeError,IndexError):continue
    return made


def content_context(c,mid,agent,*,commercial,json,status):
    if agent not in ('HERMES','SENTINEL'):return None
    scope=commercial.scope(c,mid)
    if not scope or scope['state']!='actif' or scope['mission_state']!='en cours' or scope['mode']!='cloud' or scope['project_state']!='active':
        return None
    flags=json.loads(scope['permissions'])
    if not flags.get('market') or (agent=='SENTINEL' and not flags.get('tests')):return None
    out=status(c,scope['project'])
    out['drafts']=out['drafts'][:3]
    return out
