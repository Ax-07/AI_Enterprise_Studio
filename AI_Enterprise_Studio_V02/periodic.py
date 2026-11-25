"""Finite local standing authorization; one existing plan per fixed UTC period."""
import time,json
from decimal import Decimal
import planner,autopilot

PERIODS={'daily':86400,'weekly':604800,'monthly':2592000}
LIMIT='Autorisation interne finie, périodes fixes UTC (mois = 30 jours). Un plan par période, aucun report ni rattrapage. Plafonds globaux inchangés, pas de lancement commercial. Redémarrage : suspension; nouvelle autorisation explicite requise.'
def now():return int(time.time())
def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS periodic_grants(
        id INTEGER PRIMARY KEY, cadence TEXT NOT NULL, seconds INTEGER NOT NULL, periods INTEGER NOT NULL,
        starts INTEGER NOT NULL, expires INTEGER NOT NULL, last_seen INTEGER NOT NULL,
        total_budget INTEGER NOT NULL, period_budget INTEGER NOT NULL, per_campaign INTEGER NOT NULL,
        max_campaigns INTEGER NOT NULL, total_search INTEGER NOT NULL, period_search INTEGER NOT NULL,
        explore INTEGER NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '');
        CREATE UNIQUE INDEX IF NOT EXISTS periodic_one_active ON periodic_grants(state) WHERE state='active';
        CREATE TABLE IF NOT EXISTS periodic_slots(
        grant_id INTEGER NOT NULL REFERENCES periodic_grants(id),slot INTEGER NOT NULL,
        starts INTEGER NOT NULL,expires INTEGER NOT NULL,plan INTEGER NOT NULL UNIQUE REFERENCES enterprise_plans(id),
        PRIMARY KEY(grant_id,slot));
        CREATE TABLE IF NOT EXISTS periodic_events(
        id INTEGER PRIMARY KEY,grant_id INTEGER NOT NULL REFERENCES periodic_grants(id),at INTEGER NOT NULL,event TEXT NOT NULL,detail TEXT NOT NULL);""")
    for g in c.execute("SELECT id FROM periodic_grants WHERE state='active'").fetchall():
        change(c,g['id'],'suspended','Redémarrage : aucune reprise automatique.',now())
def log(c,gid,event,detail,t):
    c.execute('INSERT INTO periodic_events(grant_id,at,event,detail) VALUES(?,?,?,?)',(gid,t,event,json.dumps(detail,ensure_ascii=False)))
def change(c,gid,state,reason,t):
    c.execute('UPDATE periodic_grants SET state=?,reason=? WHERE id=?',(state,reason,gid))
    log(c,gid,state,{'reason':reason},t)
def latest(c):
    return c.execute('SELECT * FROM periodic_grants ORDER BY id DESC LIMIT 1').fetchone()
def active(c):
    return c.execute("SELECT * FROM periodic_grants WHERE state='active'").fetchone()
def slots(c,gid):
    out=[]
    for row in c.execute("""SELECT sl.*,p.state,p.reason,p.budget,p.search_cap FROM periodic_slots sl
        JOIN enterprise_plans p ON p.id=sl.plan WHERE grant_id=? ORDER BY slot""",(gid,)):
        spent,searched=planner.totals(c,row['plan'])
        out.append({**dict(row),'spent':spent,'searches':searched})
    return out
def status(c,cfg,gid=None):
    g=latest(c) if gid is None else c.execute('SELECT * FROM periodic_grants WHERE id=?',(gid,)).fetchone()
    if not g:return {'grant':None,'limit':LIMIT}
    rows=slots(c,g['id']);spent=sum(x['spent'] for x in rows);searched=sum(x['searches'] for x in rows)
    t=now();slot=max(0,(t-g['starts'])//g['seconds'])
    return {'grant':{**dict(g),'slots':rows,'spent':spent,'searches':searched,
        'remaining':max(0,g['total_budget']-spent),'search_remaining':max(0,g['total_search']-searched),
        'current_slot':slot+1 if slot<g['periods'] else None,
        'next_boundary':min(g['expires'],g['starts']+(slot+1)*g['seconds']),
        'events':[{**dict(e),'detail':json.loads(e['detail'])} for e in c.execute('SELECT * FROM periodic_events WHERE grant_id=? ORDER BY id',(g['id'],))]},'limit':LIMIT}
def guard_manual(c):
    if active(c):raise ValueError('Autorisation périodique active : révoquer avant une opération manuelle.')
def linked_plan(c,pid):
    return c.execute("""SELECT sl.*,g.state AS grant_state,g.expires AS grant_expires,g.last_seen
        FROM periodic_slots sl JOIN periodic_grants g ON g.id=sl.grant_id WHERE sl.plan=?""",(pid,)).fetchone()
def linked_campaign(c,cid):
    row=c.execute('SELECT plan FROM enterprise_plan_queue WHERE campaign=?',(cid,)).fetchone()
    return linked_plan(c,row['plan']) if row else None
def assert_window(row,t=None):
    t=now() if t is None else t
    if row and (row['grant_state']!='active' or t<row['starts'] or t<row['last_seen'] or t>=min(row['expires'],row['grant_expires'])):
        raise ValueError('Autorisation périodique suspendue, révoquée ou hors période.')
def guard_plan(c,pid):assert_window(linked_plan(c,pid))
def guard_campaign(c,cid):assert_window(linked_campaign(c,cid))
def guard_mission(c,mid):
    row=c.execute('SELECT campaign FROM campaign_missions WHERE mission=?',(mid,)).fetchone()
    if row:guard_campaign(c,row['campaign'])
def deny_manual_plan_resume(c,pid):
    if linked_plan(c,pid):raise ValueError('Plan périodique : aucune reprise manuelle; abandonner le plan suspendu puis autoriser un nouveau travail.')
def deny_manual_campaign_resume(c,cid):
    if linked_campaign(c,cid):raise ValueError('Campagne périodique : reprise hors autorisation interdite.')
def previous_steps(c,pid):
    link=linked_plan(c,pid)
    if not link:return set()
    return {(r['project'],r['kind'],r['artifact']) for r in c.execute("""SELECT q.project,q.kind,q.artifact
        FROM enterprise_plan_queue q JOIN periodic_slots sl ON sl.plan=q.plan WHERE sl.grant_id=?""",(link['grant_id'],))}
def authorize(c,body,cfg,t=None):
    t=now() if t is None else t
    if set(body)!={'confirm','cadence','periods','total_budget','period_budget','per_campaign','max_campaigns','total_search','period_search','explore'} or body['confirm'] is not True:
        raise ValueError('Confirmation et paramètres périodiques complets requis')
    if active(c):raise ValueError('Révoquer l’autorisation active avant d’en créer une autre')
    remaining=planner._idle(c,cfg);old=planner.latest(c)
    if old and old['state']=='paused':raise ValueError('Abandonner ou traiter le plan suspendu avant autorisation')
    ca=autopilot.status(c,cfg)
    if ca and ca['recoverable']:raise ValueError('Campagne récupérable : diagnostic requis avant autorisation')
    cadence=body['cadence'];count=body['periods'];maxc=body['max_campaigns']
    if not isinstance(cadence,str) or cadence not in PERIODS or type(count) is not int or not 1<=count<=12 or type(maxc) is not int or not 1<=maxc<=5:
        raise ValueError('Cadence, 1–12 périodes et 1–5 campagnes par période requis')
    total=planner._money(body['total_budget']);period=planner._money(body['period_budget']);per=planner._money(body['per_campaign'])
    if not 10000<=per<=period<=total<=remaining or total>period*count:
        raise ValueError(f'Enveloppes invalides : campagne ≤ période ≤ total ≤ solde global {remaining/1e6:.6f} USD ; total ≤ période × nombre de périodes.')
    ts=body['total_search'];ps=body['period_search'];explore=body['explore']
    available=max(0,cfg['limit']-c.execute('SELECT COUNT(*) FROM searches').fetchone()[0])
    if type(ts) is not int or type(ps) is not int or not 0<=ps<=min(10,ts) or not 0<=ts<=min(available,ps*count) or (ts and (not ps or not cfg['brave'] or not cfg['mission_search_limit'])):
        raise ValueError('Quotas Brave invalides : total dans le solde global, maximum 10 par période.')
    if type(explore) is not bool or (explore and not ps):raise ValueError('Exploration : quota Brave positif requis')
    gid=c.execute("""INSERT INTO periodic_grants(cadence,seconds,periods,starts,expires,last_seen,total_budget,period_budget,per_campaign,
        max_campaigns,total_search,period_search,explore,state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",
        (cadence,PERIODS[cadence],count,t,t+PERIODS[cadence]*count,t,total,period,per,maxc,ts,ps,int(explore))).lastrowid
    log(c,gid,'authorized',{'periods':count,'total_budget':total,'total_search':ts},t)
    return gid
def stop_linked(c,gid):
    for sl in slots(c,gid):
        if sl['state']=='active':planner.stop(c,sl['plan']);planner.abandon(c,sl['plan'])
def revoke(c,gid,t=None):
    t=now() if t is None else t
    g=c.execute('SELECT * FROM periodic_grants WHERE id=?',(gid,)).fetchone()
    if not g or g['state'] not in ('active','suspended'):raise ValueError('Autorisation active ou suspendue requise')
    stop_linked(c,gid);change(c,gid,'revoked','Révocation propriétaire; engagements et historique conservés.',t)
def tick(c,cfg,t=None,locked=False):
    """Single transaction, caller serializes HTTP mutation and scheduler. No provider calls."""
    t=now() if t is None else t;g=active(c)
    if not g:return None
    gid=g['id'];rows=slots(c,gid)
    if t<g['last_seen']:
        stop_linked(c,gid);change(c,gid,'suspended','Horloge reculée; nouvelle autorisation requise.',t);return None
    c.execute('UPDATE periodic_grants SET last_seen=? WHERE id=?',(t,gid))
    live=next((x for x in rows if x['state']=='active'),None)
    if live and t>=min(live['expires'],g['expires']):
        stop_linked(c,gid);change(c,gid,'suspended','Période terminée pendant le travail; aucun rattrapage.',t);return None
    if t>=g['expires']:
        change(c,gid,'expired','Durée autorisée terminée.',t);return None
    if live:return None
    if any(x['state'] in ('blocked','paused','abandoned') for x in rows):
        change(c,gid,'suspended','Plan arrêté ou bloqué : examen propriétaire requis.',t);return None
    if locked:return None
    slot=(t-g['starts'])//g['seconds']
    if any(x['slot']==slot for x in rows):return None
    spent=sum(x['spent'] for x in rows);searched=sum(x['searches'] for x in rows)
    remaining=autopilot.readiness(c,cfg)
    if not remaining['ready']:
        change(c,gid,'suspended','; '.join(remaining['blockers']),t);return None
    amount=min(g['period_budget'],g['total_budget']-spent,remaining['remaining'])
    if amount<10000:
        change(c,gid,'exhausted','Budget autorisé ou global épuisé.',t);return None
    avail=max(0,cfg['limit']-c.execute('SELECT COUNT(*) FROM searches').fetchone()[0])
    cap=max(0,min(g['period_search'],g['total_search']-searched,avail)) if cfg['brave'] and cfg['mission_search_limit'] else 0
    prior={(r['project'],r['kind'],r['artifact']) for r in c.execute("""SELECT q.project,q.kind,q.artifact FROM enterprise_plan_queue q
        JOIN periodic_slots sl ON sl.plan=q.plan WHERE sl.grant_id=?""",(gid,))}
    items=[x for x in planner.candidates(c,cap)['ready'] if (x['project'],x['kind'],x['artifact']) not in prior]
    explore=bool(g['explore'] and cap and (None,'opportunity',None) not in prior)
    if not items and not explore:
        change(c,gid,'exhausted','Aucune nouvelle étape admissible dans cette autorisation.',t);return None
    def usd(v):return format(Decimal(v)/1000000,'f')
    body={'confirm':True,'budget':usd(amount),'per_campaign':usd(min(amount,g['per_campaign'])),'max_campaigns':g['max_campaigns'],'search_cap':cap,'explore':explore}
    c.execute('SAVEPOINT periodic_allocate')
    try:
        pid=planner.start(c,body,cfg)
        start=g['starts']+slot*g['seconds'];end=start+g['seconds']
        c.execute('INSERT INTO periodic_slots(grant_id,slot,starts,expires,plan) VALUES(?,?,?,?,?)',(gid,slot,start,end,pid))
        log(c,gid,'allocated',{'slot':slot,'plan':pid,'budget':amount,'search_cap':cap},t)
    except ValueError as e:
        c.execute('ROLLBACK TO periodic_allocate');c.execute('RELEASE periodic_allocate')
        change(c,gid,'suspended',str(e)[:300],t);return None
    c.execute('RELEASE periodic_allocate')
    return pid
def loop(s,shutdown):
    # Only invoked by real local server main; never on import or tests.
    while not shutdown.wait(2):
        try:
            with s.POST_LOCK:
                with s.db() as c:
                    if not active(c):continue
                cfg=s.config()
                with s.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    pid=tick(c,cfg,locked=s.LOCK.locked() or planner.RUN_LOCK.locked())
                if pid is not None:
                    s.threading.Thread(target=planner.worker,args=(s,pid),daemon=True).start()
        except Exception as e:
            # Fail closed, no endless automatic retry after an unexpected exception.
            try:
                with s.POST_LOCK,s.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    g=active(c)
                    if g:stop_linked(c,g['id']);change(c,g['id'],'suspended','Erreur ordonnanceur : '+type(e).__name__,now())
            except Exception:pass
            # A later explicit authorization may use this scheduler again.
            continue
