"""One explicit independent audit of an exact saved draft from a budget-blocked creation.
Original plan, campaign, mission, ledger and authorization stay immutable."""
import hashlib,json
LIMIT='Audit interne séparé, aucune reprise des anciennes autorisations, aucune réécriture. Un essai par fichier exact. Une preuve réussie ne certifie ni la totalité du produit ni la demande.'
def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS draft_recoveries(
        artifact INTEGER PRIMARY KEY REFERENCES artifacts(id),sha256 TEXT NOT NULL,
        source_mission INTEGER NOT NULL REFERENCES missions(id),source_campaign INTEGER NOT NULL REFERENCES campaigns(id),
        project INTEGER NOT NULL REFERENCES projects(id),campaign INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
        budget INTEGER NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP)""")
def sha(a):return hashlib.sha256(a['content'].encode()).hexdigest()
def candidates(c):
    import portfolio
    out=[]
    for a in c.execute("""SELECT a.*,m.error,ca.id AS source_campaign,pm.project
        FROM artifacts a JOIN missions m ON m.id=a.mission
        JOIN campaign_missions cm ON cm.mission=m.id JOIN campaigns ca ON ca.id=cm.campaign
        JOIN project_missions pm ON pm.mission=m.id JOIN projects p ON p.id=pm.project
        WHERE a.agent='NEXUS' AND m.mode='cloud' AND m.engine='dynamic' AND m.state='bloquée'
        AND ca.state='bloqué' AND cm.kind='create' AND p.state='active'
        AND NOT EXISTS(SELECT 1 FROM draft_recoveries d WHERE d.artifact=a.id)
        AND a.id=(SELECT MAX(b.id) FROM artifacts b WHERE b.mission=a.mission AND b.name=a.name)
        ORDER BY a.id DESC""").fetchall():
        if a['error']!='Enveloppe Autopilote insuffisante pour réserver cet appel.' and not (
            a['error'].startswith(('Enveloppe Autopilote insuffisant(e) :','Budget de mission insuffisant(e) :','Budget logiciel insuffisant(e) :')) and
            c.execute("SELECT 1 FROM budget_decisions WHERE mission=? AND decision='refused'",(a['mission'],)).fetchone()):continue
        if not a['name'].lower().endswith(('.html','.csv','.json')) or not a['content'].strip():continue
        if portfolio.latest(c,a['project']):continue
        if c.execute("SELECT 1 FROM ledger WHERE mission=? AND (actual IS NULL OR state!='mesuré')",(a['mission'],)).fetchone():continue
        digest=sha(a);found=False
        for e in c.execute("SELECT args,result FROM events WHERE mission=? AND agent='NEXUS' AND action='write_file' AND ok=1",(a['mission'],)):
            try:
                args,result=json.loads(e['args']),json.loads(e['result'])
                if result.get('fichier')==a['id'] and args.get('text_sha256')==digest:found=True;break
            except (TypeError,ValueError,AttributeError):continue
        if not found:continue
        out.append({'artifact':a['id'],'name':a['name'],'sha256':digest,'source_mission':a['mission'],'source_campaign':a['source_campaign'],'project':a['project'],'size':len(a['content'])})
    return out
def record(c,cid):return c.execute('SELECT * FROM draft_recoveries WHERE campaign=?',(cid,)).fetchone()
def choose(c,cid):
    row=record(c,cid)
    if not row:return None
    a=c.execute('SELECT * FROM artifacts WHERE id=?',(row['artifact'],)).fetchone()
    if not a or sha(a)!=row['sha256']:raise ValueError('Empreinte du brouillon modifiée')
    if c.execute('SELECT 1 FROM campaign_missions WHERE campaign=?',(cid,)).fetchone():return None
    return ('functional',a['id'],None)
def start(c,body,cfg):
    import planner,autopilot,periodic,connectors,portfolio
    if set(body)!={'confirm','artifact','sha256','budget'} or body['confirm'] is not True or type(body['artifact']) is not int:raise ValueError('Autorisation du brouillon exact requise')
    periodic.guard_manual(c);remaining=planner._idle(c,cfg)
    last=planner.latest(c)
    if last and last['state']=='paused':raise ValueError('Abandonner le plan suspendu avant audit')
    item=next((x for x in candidates(c) if x['artifact']==body['artifact'] and x['sha256']==body['sha256']),None)
    if not item:raise ValueError('Brouillon non admissible, modifié ou déjà audité')
    if item['name'].lower().endswith('.html') and not cfg.get('html_sandbox_enabled'):raise ValueError('Sandbox HTML non activée : aucun audit facturable lancé')
    budget=planner._money(body['budget'])
    if budget>remaining or budget>cfg['mission_budget']:raise ValueError('Enveloppe supérieure au solde global ou au plafond mission')
    flags={'research':False,'production':False,'tests':True,'market':False}
    cid=c.execute("""INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,source,state)
        VALUES(?,?,1,?,0,?,'actif')""",('Récupérer par audit indépendant le brouillon exact #'+str(item['artifact'])+' ; ne pas recréer ni modifier.',budget,json.dumps(flags),item['artifact'])).lastrowid
    c.execute("INSERT INTO campaign_projects(campaign,project,scope) VALUES(?,?,'draft_recovery')",(cid,item['project']))
    c.execute("""INSERT INTO draft_recoveries(artifact,sha256,source_mission,source_campaign,project,campaign,budget)
        VALUES(?,?,?,?,?,?,?)""",(item['artifact'],item['sha256'],item['source_mission'],item['source_campaign'],item['project'],cid,budget))
    connectors.authorize_campaign(c,cid,{'connector_cap':0,'connector_budget':'0'})
    return cid
def verdict(c,row):
    import autopilot
    a=c.execute('SELECT * FROM artifacts WHERE id=?',(row['artifact'],)).fetchone()
    if not a or sha(a)!=row['sha256']:return 'modified'
    ca=autopilot._campaign(c,row['campaign'])
    ms=autopilot._missions(c,row['campaign'])
    if ca['state']=='actif':return 'active'
    if ca['state']!='terminé' or len(ms)!=1 or ms[0]['state']!='terminée' or ms[0]['artifact']!=a['id']:return 'incomplete'
    proof=autopilot._proof(c,a['id'],ms[0]['id'])
    return 'adopted' if proof=='passed' else proof
def adopted(c,pid):
    for row in c.execute('SELECT * FROM draft_recoveries WHERE project=? ORDER BY artifact DESC',(pid,)):
        if verdict(c,row)=='adopted':return c.execute('SELECT * FROM artifacts WHERE id=?',(row['artifact'],)).fetchone()
    return None
def history(c):
    return [{**dict(x),'verdict':verdict(c,x)} for x in c.execute('SELECT * FROM draft_recoveries ORDER BY campaign DESC')]
def status(c):
    return {'candidates':candidates(c),'history':history(c),'limit':LIMIT}
