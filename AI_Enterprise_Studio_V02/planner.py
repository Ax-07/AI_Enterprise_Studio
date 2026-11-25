"""Persistent bounded orchestration, reuses the existing campaign engine."""
import json,hashlib,threading,re,unicodedata
from decimal import Decimal,InvalidOperation
import autopilot,portfolio,commercial,collective_evidence,laboratory

LIMIT='Plan interne borné, aucun achat, contact, publication ou vente. Score économique hypothétique. Aucun démarrage automatique au redémarrage. Les budgets et quotas existants restent applicables.'
RUN_LOCK=threading.Lock()
FLAGS={'research':True,'production':True,'tests':True,'market':True}
GOAL='Faire progresser une activité interne avec preuves exactes, sans répéter les expériences ni lancer une vente.'

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS enterprise_plans(
        id INTEGER PRIMARY KEY,budget INTEGER NOT NULL,per_campaign INTEGER NOT NULL,
        max_campaigns INTEGER NOT NULL,search_cap INTEGER NOT NULL,explore INTEGER NOT NULL,
        state TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE UNIQUE INDEX IF NOT EXISTS enterprise_plan_active ON enterprise_plans(state) WHERE state='active';
        CREATE TABLE IF NOT EXISTS enterprise_plan_queue(
        id INTEGER PRIMARY KEY,plan INTEGER NOT NULL REFERENCES enterprise_plans(id),
        project INTEGER REFERENCES projects(id),artifact INTEGER REFERENCES artifacts(id),
        kind TEXT NOT NULL,reason TEXT NOT NULL,campaign INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
        created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS enterprise_plan_queue_plan ON enterprise_plan_queue(plan,id);
        CREATE TABLE IF NOT EXISTS enterprise_plan_events(
        id INTEGER PRIMARY KEY,plan INTEGER NOT NULL REFERENCES enterprise_plans(id),
        event TEXT NOT NULL,detail TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);""")
    for row in c.execute("SELECT id FROM enterprise_plans WHERE state='active'").fetchall():
        change(c,row['id'],'paused','Redémarrage : reprise explicite requise, campagnes et compteurs conservés.')

def active(c):
    return c.execute("SELECT 1 FROM enterprise_plans WHERE state='active'").fetchone() is not None

def guard_manual(c):
    if active(c):raise ValueError('Plan continu actif : arrêter le plan avant toute autre opération.')

def log(c,pid,event,detail):
    c.execute('INSERT INTO enterprise_plan_events(plan,event,detail) VALUES(?,?,?)',(pid,event,json.dumps(detail,ensure_ascii=False)))

def change(c,pid,state,reason):
    c.execute('UPDATE enterprise_plans SET state=?,reason=? WHERE id=?',(state,reason,pid))
    log(c,pid,state,{'reason':reason})

def get(c,pid):
    return c.execute('SELECT * FROM enterprise_plans WHERE id=?',(pid,)).fetchone()

def latest(c):
    return c.execute('SELECT * FROM enterprise_plans ORDER BY id DESC LIMIT 1').fetchone()

def queue(c,pid):
    return [dict(x) for x in c.execute("""SELECT q.*,ca.state,ca.reason AS campaign_reason,ca.budget AS campaign_budget,
        p.title,a.name AS artifact_name FROM enterprise_plan_queue q JOIN campaigns ca ON ca.id=q.campaign
        LEFT JOIN projects p ON p.id=q.project LEFT JOIN artifacts a ON a.id=q.artifact
        WHERE q.plan=? ORDER BY q.id""",(pid,))]

def totals(c,pid):
    items=queue(c,pid)
    return sum(autopilot.costs(c,x['campaign']) for x in items),sum(autopilot.searches(c,x['campaign']) for x in items)

def assessment(c,oid):
    if oid is None:return None
    row=c.execute("""SELECT o.*,a.id AS assessment_id,a.agent AS assessment_agent,a.assumptions,
        a.source_runs,a.result,a.opportunity_sha256 FROM opportunities o JOIN market_assessments a ON a.opportunity=o.id
        JOIN missions m ON m.id=a.mission WHERE o.id=? AND a.mission=o.mission AND m.mode='cloud'
        AND m.state='terminée' AND a.id=(SELECT MAX(b.id) FROM market_assessments b WHERE b.opportunity=o.id)""",(oid,)).fetchone()
    if not row:return None
    try:return collective_evidence.assessment(c,row)
    except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError):return None

def attempted_commercial(c,pid,aid):
    return c.execute("""SELECT 1 FROM campaign_projects cp JOIN campaigns ca ON ca.id=cp.campaign
        WHERE cp.project=? AND cp.scope='commercial' AND ca.source IS ? LIMIT 1""",(pid,aid)).fetchone() is not None

def related(c):
    """Conservative lexical suggestions only. No merged IDs or evidence transfer."""
    rows=[dict(x) for x in c.execute("SELECT id,title FROM projects WHERE state='active' ORDER BY id")]
    def terms(title):
        t=unicodedata.normalize('NFKD',title.lower())
        t=''.join(x for x in t if not unicodedata.combining(x))
        words=set(re.findall(r'[a-z]{4,}',t))
        return {('commerce' if w.startswith('commerc') else w.rstrip('s')) for w in words}-{'pour','avec','automatique','automatise','automatisation','controle','qualite','fichier','produit','outil'}
    out=[]
    for i,x in enumerate(rows):
        for y in rows[i+1:]:
            a,b=terms(x['title']),terms(y['title']);shared=a&b
            if len(shared)>=2 and (len(shared)/max(1,min(len(a),len(b)))>=.5 or {'commerce','multilingue'}.issubset(shared)):
                out.append({'projects':[x['id'],y['id']],'titles':[x['title'],y['title']],'shared_terms':sorted(shared),'classification':'similarité lexicale à examiner; aucune équivalence démontrée'})
    return out[:30]

def candidates(c,search_cap=0):
    """Read only, exact portfolio lineage, deterministic ordering, never infer product equivalence."""
    ready=[];held=[]
    for p in c.execute('SELECT * FROM projects ORDER BY id'):
        pid=p['id'];art=portfolio.latest(c,pid);aid=art['id'] if art else None
        record={'project':pid,'title':p['title'],'artifact':aid,'artifact_name':art['name'] if art else None}
        assessed=assessment(c,p['opportunity'])
        score=assessed['result']['score'] if assessed else None
        record['score']=score
        def hold(reason):held.append({**record,'reason':reason})
        if p['state']!='active':hold('Activité suspendue ou archivée.');continue
        if assessed and not assessed['result']['scenario_viable']:
            hold('Scénario économique non viable; réexamen explicite requis.');continue
        offer=commercial.project_status(c,pid)['offer']
        if offer and offer['economics'] and offer['economics']['result']['monthly_result_cents']<=0:
            hold('Dernière offre évaluée déficitaire; réexamen explicite requis.');continue
        # Do not auto-create from an unassessed or invalid assessment.
        if not art and not assessed:hold('Évaluation économique vérifiée manquante.');continue
        step,reason=portfolio.next_step(c,pid,FLAGS)
        if step and step[0]=='laboratory':
            sha=hashlib.sha256(art['content'].encode()).hexdigest()
            if c.execute('SELECT 1 FROM laboratory_runs WHERE artifact=? AND sha256=? AND profile=? AND revision=? AND size=300 AND seed=?',(aid,sha,laboratory.PROFILE,laboratory.VERSION,laboratory.DEFAULT_SEED)).fetchone():
                hold('Banc d’essai déjà tenté sur cette version; examen requis.');continue
        if art:
            proofs=portfolio.evidence(c,art)
            independent=any(x['agent']=='SENTINEL' and x['status']=='passed' for x in proofs) and not any(x['agent']=='SENTINEL' and x['status']=='failed' for x in proofs)
            if laboratory.supports(art):
                lab=laboratory.canonical(c,art);independent=independent and bool(lab and lab['status']=='passed')
            follow=commercial.eligible_followup(c,pid,aid) if independent else None
            if follow and search_cap>0:
                ready.append({**record,'kind':'commercial','base_offer':follow['id'],'priority':-1,'reason':'Compléter les preuves documentaires de l’offre #'+str(follow['id'])+' sans refaire l’offre ni les calculs.'});continue
            if independent and not attempted_commercial(c,pid,aid):
                ready.append({**record,'kind':'commercial','priority':0,'reason':'Produit exact et preuves indépendantes disponibles; préparer une offre sans lancement.'});continue
            if independent and (not step or step[0]=='market'):
                hold('Complément possible avec quota Brave positif.' if follow else 'Préparation commerciale déjà autorisée sur cette référence; aucun nouveau signal justifiant une répétition.');continue
        if not step:hold(reason);continue
        kind,ref,_=step
        if kind not in ('create','improve','functional','laboratory'):
            hold('Étape non retenue par le planificateur.');continue
        ready.append({**record,'artifact':ref,'kind':kind,'priority':1 if kind in ('functional','laboratory','improve') else 2,'reason':reason})
    return {'ready':sorted(ready,key=lambda x:(x['priority'],-(x['score'] or 0),x['project'])),'held':held,'related':related(c),'limit':LIMIT}

def status(c):
    row=latest(c);preview=candidates(c)
    with_search=candidates(c,3)
    preview['documentary_candidates']=[x for x in with_search['ready'] if x.get('base_offer')]
    if not row:return {'plan':None,'preview':preview,'limit':LIMIT}
    d=dict(row);d['queue']=queue(c,row['id']);d['spent'],d['searches']=totals(c,row['id'])
    d['remaining']=max(0,d['budget']-d['spent'])
    d['events']=[{**dict(e),'detail':json.loads(e['detail'])} for e in c.execute('SELECT * FROM enterprise_plan_events WHERE plan=? ORDER BY id',(row['id'],))]
    return {'plan':d,'preview':preview,'limit':LIMIT}

def _money(raw):
    try:
        if not isinstance(raw,str) or len(raw)>12:raise ValueError()
        d=Decimal(raw)*1000000
        if not d.is_finite() or d!=d.to_integral_value() or not 10000<=d<=10000000:raise ValueError()
        return int(d)
    except (InvalidOperation,ValueError,OverflowError):raise ValueError('Budget décimal entre 0,01 et 10 USD requis')

def _idle(c,cfg):
    ready=autopilot.readiness(c,cfg)
    if not ready['ready']:raise ValueError('; '.join(ready['blockers']))
    if active(c):raise ValueError('Un plan est déjà actif')
    return ready['remaining']

def start(c,body,cfg):
    if set(body)!= {'confirm','budget','per_campaign','max_campaigns','search_cap','explore'} or body['confirm'] is not True:
        raise ValueError('Autorisation explicite et paramètres complets requis')
    old=latest(c)
    if old and old['state']=='paused':raise ValueError('Reprendre ou abandonner le plan suspendu')
    remaining=_idle(c,cfg)
    last=autopilot.status(c,cfg)
    if last and last['recoverable']:raise ValueError('Une campagne récupérable existe; la traiter avant un nouveau plan')
    budget=_money(body['budget']);per=_money(body['per_campaign'])
    count=body['max_campaigns'];cap=body['search_cap'];explore=body['explore']
    if not 10000<=per<=budget<=remaining or type(count) is not int or not 1<=count<=5:raise ValueError('Enveloppes ou nombre de campagnes invalides')
    available=max(0,cfg['limit']-c.execute('SELECT COUNT(*) FROM searches').fetchone()[0])
    if type(cap) is not int or not 0<=cap<=min(10,available) or (cap and not cfg['brave']) or type(explore) is not bool or (explore and not cap):raise ValueError('Quota Brave ou autorisation exploration invalide')
    portfolio.sync(c)
    pid=c.execute("""INSERT INTO enterprise_plans(budget,per_campaign,max_campaigns,search_cap,explore,state)
        VALUES(?,?,?,?,?,'active')""",(budget,per,count,cap,int(explore))).lastrowid
    log(c,pid,'authorized',{'budget':budget,'per_campaign':per,'max_campaigns':count,'search_cap':cap,'explore':explore})
    return pid

def stop(c,pid):
    p=get(c,pid)
    if not p or p['state']!='active':raise ValueError('Plan non actif')
    rows=queue(c,pid)
    if rows and rows[-1]['state']=='actif':autopilot.stop(c,rows[-1]['campaign'])
    change(c,pid,'paused','Arrêt demandé; appels déjà réservés conservés.')

def abandon(c,pid):
    p=get(c,pid)
    if not p or p['state']!='paused':raise ValueError('Seul un plan suspendu peut être abandonné')
    change(c,pid,'abandoned','Plan abandonné explicitement; historique et campagnes conservés.')

def resume(c,pid,cfg):
    p=get(c,pid)
    if not p or p['state']!='paused' or latest(c)['id']!=pid:raise ValueError('Plan suspendu le plus récent requis')
    remaining=_idle(c,cfg)
    spent,searched=totals(c,pid)
    if spent>=p['budget'] or remaining<10000:raise ValueError('Budget restant insuffisant')
    rows=queue(c,pid)
    if rows and rows[-1]['state'] in ('interrompu','arrêté'):
        # Child retains original authorization; no allocation or counter reset.
        child=rows[-1]
        if child['campaign_budget']-autopilot.costs(c,child['campaign'])>min(p['budget']-spent,remaining):raise ValueError('Enveloppe restante insuffisante pour reprendre la campagne')
        autopilot.resume(c,child['campaign'],cfg)
    elif rows and rows[-1]['state']!='terminé':raise ValueError('Campagne à diagnostiquer; abandonner le plan avant une reprise manuelle')
    change(c,pid,'active','Reprise explicite du plan sans remise à zéro.')

def next_campaign(c,pid,cfg):
    """Called under BEGIN IMMEDIATE. Return an existing or newly allocated campaign ID."""
    p=get(c,pid)
    if not p or p['state']!='active':return None
    rows=queue(c,pid)
    if rows and rows[-1]['state']=='actif':return rows[-1]['campaign']
    if rows and rows[-1]['state']!='terminé':
        child=rows[-1];cid=child['campaign']
        # Only one automatic recovery per linked campaign; no quota renewal.
        st=autopilot.status(c,cfg,cid)
        prior=any(json.loads(e[0]).get('campaign')==cid for e in c.execute("SELECT detail FROM enterprise_plan_events WHERE plan=? AND event='recovered'",(pid,)))
        if child['state']=='bloqué' and not prior and st['recovery_kind'] in ('transient','commercial') and autopilot.readiness(c,cfg)['ready']:
            spent,_=totals(c,pid)
            if child['campaign_budget']-autopilot.costs(c,cid)<=p['budget']-spent:
                c.execute('SAVEPOINT recovery_attempt')
                try:
                    autopilot.resume(c,cid,cfg)
                    log(c,pid,'recovered',{'campaign':cid,'kind':st['recovery_kind'],'spent_before':spent})
                except ValueError:
                    c.execute('ROLLBACK TO recovery_attempt');c.execute('RELEASE recovery_attempt')
                else:
                    c.execute('RELEASE recovery_attempt');return cid
        change(c,pid,'blocked','Campagne #'+str(cid)+' : '+child['campaign_reason']);return None
    if len(rows)>=p['max_campaigns']:
        change(c,pid,'completed','Nombre maximal de campagnes atteint.');return None
    ready=autopilot.readiness(c,cfg)
    if not ready['ready']:
        change(c,pid,'blocked','; '.join(ready['blockers']));return None
    spent,searched=totals(c,pid)
    amount=min(p['budget']-spent,p['per_campaign'],ready['remaining'])
    if amount<10000:
        change(c,pid,'completed','Budget restant insuffisant pour une nouvelle campagne.');return None
    portfolio.sync(c)
    available=max(0,cfg['limit']-c.execute('SELECT COUNT(*) FROM searches').fetchone()[0])
    cap=min(3,max(0,p['search_cap']-searched),available) if cfg['brave'] else 0
    preview=candidates(c,cap)
    tried={(x['project'],x['kind'],x['artifact']) for x in rows}
    items=[x for x in preview['ready'] if (x['project'],x['kind'],x['artifact']) not in tried]
    item=items[0] if items else None
    if not item and p['explore'] and cap and not any(x['kind']=='opportunity' for x in rows):
        recent=c.execute("""SELECT 1 FROM campaign_missions cm JOIN missions m ON m.id=cm.mission
            WHERE cm.kind='opportunity' AND m.created>=datetime('now','-1 day')""").fetchone()
        if not recent:item={'project':None,'artifact':None,'kind':'opportunity','reason':'Exploration explicitement autorisée, une fois au maximum.'}
    if not item:
        log(c,pid,'no_candidate',{'held':preview['held']})
        change(c,pid,'completed','Aucune nouvelle étape admissible; activités conservées sans répétition.');return None
    kind=item['kind'];flags=dict(FLAGS)
    if kind=='commercial':flags['production']=False
    elif kind=='opportunity':flags['production']=False
    else:flags['research']=False;flags['market']=False;cap=0
    body={'confirm':True,'goal':GOAL,'budget':format(Decimal(amount)/1000000,'f'),'max_missions':1,
        'permissions':flags,'search_cap':cap,'connector_cap':0,'connector_budget':'0',
        'project':item['project'] if item['project'] is not None else 'explore',
        'campaign_mode':'commercial' if kind=='commercial' else 'explore' if kind=='opportunity' else 'progression'}
    if kind=='commercial':
        body['commercial']=True
        if item.get('base_offer'):body['commercial_followup']=item['base_offer']
    cid=autopilot.start(c,body,cfg)
    # Verify exact selection before committing. Rollback whole allocation on drift.
    selected=autopilot.choose(c,autopilot._campaign(c,cid))[0]
    if not selected or selected[0]!=kind or selected[1]!=item['artifact']:raise ValueError('Étape sélectionnée différente du plan')
    c.execute('INSERT INTO enterprise_plan_queue(plan,project,artifact,kind,reason,campaign) VALUES(?,?,?,?,?,?)',
        (pid,item['project'],item['artifact'],kind,item['reason'],cid))
    log(c,pid,'allocated',{'campaign':cid,'kind':kind,'project':item['project'],'artifact':item['artifact'],'reason':item['reason'],'budget':amount,'search_cap':cap,'base_offer':item.get('base_offer')})
    return cid

def worker(s,pid):
    with RUN_LOCK:_worker(s,pid)

def _worker(s,pid):
    # Reuse the existing engine lock; never hold it while calling autopilot.worker.
    try:
        while True:
            cfg=s.config()
            with s.db() as c:
                c.execute('BEGIN IMMEDIATE')
                cid=next_campaign(c,pid,cfg)
            if cid is None:return
            autopilot.worker(s,cid)
    except Exception as e:
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            p=get(c,pid)
            if p and p['state']=='active':
                rows=queue(c,pid)
                if rows and rows[-1]['state']=='actif':autopilot.stop(c,rows[-1]['campaign'])
                change(c,pid,'blocked','Erreur du planificateur : '+str(e)[:300])
