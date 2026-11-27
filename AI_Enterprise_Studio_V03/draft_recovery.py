"""One explicit independent audit of an exact saved draft from a budget-blocked creation.
Original plan, campaign, mission, ledger and authorization stay immutable."""
import hashlib,json
from departments import recovery_evidence
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
    return recovery_evidence.candidates(c,latest=portfolio.latest,sha=sha,json=json)
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
    return recovery_evidence.verdict(c,row,sha=sha,campaign=autopilot._campaign,missions=autopilot._missions,proof=autopilot._proof)
def adopted(c,pid):
    for row in c.execute('SELECT * FROM draft_recoveries WHERE project=? ORDER BY artifact DESC',(pid,)):
        if verdict(c,row)=='adopted':return c.execute('SELECT * FROM artifacts WHERE id=?',(row['artifact'],)).fetchone()
    return None
def history(c):
    return [{**dict(x),'verdict':verdict(c,x)} for x in c.execute('SELECT * FROM draft_recoveries ORDER BY campaign DESC')]
def status(c):
    return {'candidates':candidates(c),'history':history(c),'limit':LIMIT}
