"""Version selection by a trusted, bounded regression gate; never run generated code on host."""
import json,hashlib
import verification,laboratory
from departments import improvement_comparison

MAX_REPLAYS=6
CSV_PROFILE='catalogue-csv-v1'
LIMIT='Comparaison technique bornée. Pas de validation commerciale, sécurité générale ou mesure de relecture.'

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS product_references(
        project INTEGER PRIMARY KEY REFERENCES projects(id), artifact INTEGER NOT NULL REFERENCES artifacts(id),
        sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS improvement_cycles(
        id INTEGER PRIMARY KEY, campaign INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
        project INTEGER NOT NULL REFERENCES projects(id), baseline INTEGER NOT NULL REFERENCES artifacts(id),
        baseline_sha TEXT NOT NULL, candidate INTEGER REFERENCES artifacts(id), candidate_sha TEXT,
        profile TEXT NOT NULL, goal TEXT NOT NULL, plan TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
        result TEXT NOT NULL DEFAULT '{}', created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS improvement_project ON improvement_cycles(project,id);
        CREATE TABLE IF NOT EXISTS reference_history(
        id INTEGER PRIMARY KEY, project INTEGER NOT NULL REFERENCES projects(id), artifact INTEGER NOT NULL REFERENCES artifacts(id),
        sha256 TEXT NOT NULL, reason TEXT NOT NULL, cycle INTEGER REFERENCES improvement_cycles(id), created TEXT DEFAULT CURRENT_TIMESTAMP);""")

def sha(row):return hashlib.sha256(row['content'].encode('utf8')).hexdigest()
def row(c,aid):return c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
def current(c,pid):
    return c.execute('SELECT * FROM product_references WHERE project=?',(pid,)).fetchone()
def pinned(c,pid):
    ref=current(c,pid)
    if not ref:return None
    a=row(c,ref['artifact'])
    if not a or sha(a)!=ref['sha256']:raise ValueError('Intégrité de la référence altérée; diagnostic requis')
    return a

def pin(c,pid,a,reason,cycle=None):
    c.execute("""INSERT INTO product_references(project,artifact,sha256) VALUES(?,?,?)
        ON CONFLICT(project) DO UPDATE SET artifact=excluded.artifact,sha256=excluded.sha256""",(pid,a['id'],sha(a)))
    c.execute('INSERT INTO reference_history(project,artifact,sha256,reason,cycle) VALUES(?,?,?,?,?)',(pid,a['id'],sha(a),reason,cycle))

def cycle(c,cid):return c.execute('SELECT * FROM improvement_cycles WHERE campaign=?',(cid,)).fetchone()

def replays(c,a):
    result=[];seen=set()
    for v in c.execute("""SELECT * FROM verification_results WHERE artifact=?
        AND agent IN ('SENTINEL','PROPRIETAIRE') ORDER BY id""",(a['id'],)):
        try:
            r=json.loads(v['result']);spec=json.loads(v['spec'])
            if r.get('sha256')!=sha(a) or r.get('status')!='passed' or not r.get('checks') or not all(x.get('passed') is True for x in r['checks']):continue
            key=json.dumps(spec,sort_keys=True,ensure_ascii=False)
            if key in seen:continue
            seen.add(key);result.append({'proof':v['id'],'spec':v['spec']})
        except (TypeError,ValueError,AttributeError):continue
    if len(result)>MAX_REPLAYS:raise ValueError('Plus de six protocoles historiques distincts; examen manuel requis')
    return result

def plan(c,a,profile):
    if not a or not a['name'].lower().endswith(('.html','.csv','.json')):raise ValueError('Produit testable HTML/CSV/JSON requis')
    if profile not in ('generic',CSV_PROFILE):raise ValueError('Profil d’amélioration inconnu')
    lab=laboratory.canonical(c,a) if laboratory.supports(a) else None
    if lab and lab['status']!='passed':raise ValueError('Banc d’essai de référence non réussi')
    if profile==CSV_PROFILE and (not laboratory.supports(a) or not lab):raise ValueError('Profil CSV : moteur catalogue et banc de référence réussi requis')
    re=replays(c,a)
    if not re and not (lab and lab['status']=='passed'):raise ValueError('Aucune preuve de référence exploitable')
    return {'replays':re,'lab':lab['id'] if lab else None,'profile':profile}

def begin(c,cid,pid,a,profile,goal,frozen):
    if not current(c,pid):pin(c,pid,a,'Référence historique conservée')
    elif pinned(c,pid)['id']!=a['id']:raise ValueError('Référence modifiée')
    c.execute("UPDATE improvement_cycles SET state='abandoned' WHERE project=? AND state='pending'",(pid,))
    c.execute("""INSERT INTO improvement_cycles(campaign,project,baseline,baseline_sha,profile,goal,plan)
        VALUES(?,?,?,?,?,?,?)""",(cid,pid,a['id'],sha(a),profile,goal,json.dumps(frozen,ensure_ascii=False)))

def feature_spec():
    return improvement_comparison.feature_spec()

def production_title(cy,a):
    instruction=('Ajoute import CSV local via input type=file #csv-file et bouton #import-csv; colonnes sku,locale,title, virgule, UTF-8; locales attendues fr-FR et en-GB. Désactive #run pendant la lecture asynchrone du CSV, puis réactive-le après mise à jour JSON. Conserve #data, #run, #out, le comportement JSON et les règles. Aucun réseau. '
                 if cy['profile']==CSV_PROFILE else '')
    return ('AMÉLIORATION — ATLAS délègue à NEXUS. Lis le fichier exact ref:'+str(a['id'])+
        '. Objectif : '+cy['goal']+' . '+instruction+'Produis une seule nouvelle version complète avec le même nom '+a['name']+
        ' dans cette nouvelle mission, sans écraser la référence. Les preuves historiques seront rejouées localement. Ne prétends pas avoir validé la candidate. Aucun lancement externe.')[:1500]

def candidate(c,cy,mid):
    # Same name and format, latest version within the dedicated production mission only.
    base=row(c,cy['baseline'])
    if not base:return None
    a=c.execute("""SELECT a.* FROM artifacts a JOIN missions m ON m.id=a.mission
        JOIN project_missions pm ON pm.mission=m.id WHERE a.mission=? AND pm.project=?
        AND m.state='terminée' AND a.agent='NEXUS' AND a.name=? ORDER BY a.version DESC,a.id DESC LIMIT 1""",
        (mid,cy['project'],base['name'])).fetchone()
    if not a or sha(a)==cy['baseline_sha']:return None
    return a

def verify_pair(base,new,frozen,profile,cfg,lab_before):
    return improvement_comparison.verify_pair(base,new,frozen,profile,cfg,lab_before,
        verification=verification,laboratory=laboratory,feature_spec=feature_spec,json=json,limit=LIMIT,csv_profile=CSV_PROFILE)

def complete(s,cid,mid,cfg):
    with s.db() as c:
        cy=cycle(c,cid)
        if not cy or cy['state']!='pending':raise ValueError('Cycle non actif')
        cy=dict(cy);base=dict(pinned(c,cy['project']))
        if base['id']!=cy['baseline'] or sha(base)!=cy['baseline_sha']:raise ValueError('Référence du cycle modifiée')
        a=candidate(c,cy,mid);a=dict(a) if a else None
        frozen=json.loads(cy['plan']);lab_before=None
        if frozen['lab'] is not None:
            r=c.execute('SELECT * FROM laboratory_runs WHERE id=? AND artifact=? AND sha256=?',(frozen['lab'],base['id'],sha(base))).fetchone()
            if r:lab_before=json.loads(r['result'])
    if a:state,result=verify_pair(base,a,frozen,cy['profile'],cfg,lab_before)
    else:state,result='rejected',{'limit':LIMIT,'reason':'Aucune nouvelle version NEXUS du produit exact.'}
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        live=cycle(c,cid);campaign=c.execute('SELECT state FROM campaigns WHERE id=?',(cid,)).fetchone()
        # An in-flight local run may finish after stop; do not promote after authorization withdrawn.
        if not live or live['state']!='pending' or not campaign or campaign['state']!='actif':return
        if pinned(c,cy['project'])['id']!=base['id'] or (a and sha(row(c,a['id']))!=sha(a)):raise ValueError('Fichier modifié pendant la comparaison')
        if a and result.get('laboratory'):
            lr=result['laboratory']['candidate']
            # Keep candidate benchmark visible in the existing laboratory without consuming the normal campaign quota.
            rid=c.execute("""INSERT INTO laboratory_runs(artifact,campaign,profile,revision,size,seed,sha256,status,result)
                VALUES(?,NULL,?,?,?,?,?,?,?)""",(a['id'],lr['profile'],lr['revision'],lr['size'],lr['seed'],lr['sha256'],lr['status'],laboratory.encode(lr))).lastrowid
            result['laboratory']['candidate_run']=rid
        c.execute('UPDATE improvement_cycles SET candidate=?,candidate_sha=?,state=?,result=? WHERE id=?',
            (a['id'] if a else None,sha(a) if a else None,state,json.dumps(result,ensure_ascii=False),cy['id']))
        if state=='retained':pin(c,cy['project'],a,'Amélioration CSV démontrée; non-régression',cy['id'])
        c.execute("UPDATE campaigns SET state='terminé',reason=? WHERE id=?",({
            'retained':'Candidate retenue sur critères techniques; aucune validation commerciale.',
            'review':'Non-régression réussie; gain non démontré automatiquement, référence conservée.',
            'rejected':'Candidate non retenue; référence intacte.'}[state],cid))

def retain_review(c,rid):
    if type(rid) is not int:raise ValueError('Cycle invalide')
    if c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone() or c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone():raise ValueError('Travail en cours')
    cy=c.execute("SELECT * FROM improvement_cycles WHERE id=? AND state='review'",(rid,)).fetchone()
    if not cy:raise ValueError('Comparaison réussie en attente de décision requise')
    ref=pinned(c,cy['project']);a=row(c,cy['candidate'])
    if ref['id']!=cy['baseline'] or sha(ref)!=cy['baseline_sha'] or not a or sha(a)!=cy['candidate_sha']:
        raise ValueError('Référence ou candidate modifiée')
    pin(c,cy['project'],a,'Sélection explicite après comparaison technique',rid)
    c.execute("UPDATE improvement_cycles SET state='retained_manual' WHERE id=?",(rid,))
    c.execute("UPDATE improvement_cycles SET state='abandoned' WHERE project=? AND state='pending'",(cy['project'],))

def restore(c,pid,aid):
    if type(pid) is not int or type(aid) is not int:raise ValueError('Identifiants invalides')
    if c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone() or c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone():raise ValueError('Travail en cours')
    a=row(c,aid)
    h=c.execute('SELECT * FROM reference_history WHERE project=? AND artifact=? ORDER BY id DESC LIMIT 1',(pid,aid)).fetchone()
    if not a or not h or sha(a)!=h['sha256']:raise ValueError('Ancienne référence intacte requise')
    pin(c,pid,a,'Restauration explicite du propriétaire')
    c.execute("UPDATE improvement_cycles SET state='abandoned' WHERE project=? AND state='pending'",(pid,))

def summary(c,cy):
    r=json.loads(cy['result']);lab=r.get('laboratory') or {};feat=r.get('feature') or {}
    return {**{k:cy[k] for k in ('id','campaign','project','baseline','candidate','profile','goal','state','created')},
        'replays':[{'proof':x['proof'],'status':x['result']['status']} for x in r.get('replays',[])],
        'baseline_metrics':lab.get('baseline_metrics'),'candidate_metrics':(lab.get('candidate') or {}).get('metrics'),
        'non_regression':lab.get('non_regression'),'feature_before':(feat.get('baseline') or {}).get('status'),
        'feature_after':(feat.get('candidate') or {}).get('status'),'reason':r.get('reason'),
        'spent':c.execute("""SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved)),0) FROM ledger l JOIN campaign_missions cm ON cm.mission=l.mission WHERE cm.campaign=?""",(cy['campaign'],)).fetchone()[0]}

def status(c,pid):
    ref=current(c,pid)
    return {'reference':ref['artifact'] if ref else None,
        'history':[dict(x) for x in c.execute('SELECT * FROM reference_history WHERE project=? ORDER BY id DESC',(pid,))],
        'cycles':[summary(c,x) for x in c.execute('SELECT * FROM improvement_cycles WHERE project=? ORDER BY id DESC',(pid,))]}

def available(c,a):
    if not a:return []
    modes=[]
    for mode in ('generic',CSV_PROFILE):
        try:plan(c,a,mode);modes.append(mode)
        except ValueError:pass
    return modes
