"""D04.2/D04.3: explicit, bounded read tools, no engine actions."""
import json
import sqlite3
import campus_commercial
import incidents
import campus_quality
import campus_infrastructure
import campus_economy
import campus_workforce
import autopilot
import planner
import periodic
from pathlib import Path

TOOLS=frozenset(('missions','work','files','artifact','memory','report','finance','opps','home','portfolio','laboratory','tools','agents','goals','owner','decisions','incidents','quality','infrastructure','economy','workforce')) | campus_commercial.TOOLS
MAX_ARTIFACT_BYTES=2*1024*1024
MAX_REPORT_BYTES=256*1024

class BadQuery(ValueError): pass
class Missing(LookupError): pass
class TooLarge(ValueError): pass

def read(path, tool, params, *, roles=None, permissions=None, registry=None, resources=None):
    if tool not in TOOLS: raise BadQuery('Outil inconnu')
    allowed={'id'} if tool in ('artifact','report') or tool in campus_commercial.DETAILS else {'q'} if tool=='memory' else set()
    if set(params)-allowed or any(len(v)!=1 for v in params.values()):
        raise BadQuery('Paramètres invalides')
    ident=None
    if tool in ('artifact','report') or tool in campus_commercial.DETAILS:
        raw=params.get('id',[''])[0]
        if not raw.isascii() or not raw.isdecimal() or len(raw)>18 or int(raw)<1:
            raise BadQuery('Identifiant invalide')
        ident=int(raw)
    term=params.get('q',[''])[0].strip()
    if tool=='memory' and not 2<=len(term)<=120:
        raise BadQuery('Recherche : 2 à 120 caractères')
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        def rows(sql,args=()):
            return [dict(r) for r in db.execute(sql,args)]
        if tool in campus_commercial.TOOLS:
            result=campus_commercial.read(db,tool,ident)
            if tool in campus_commercial.DETAILS and not result:raise Missing('Dossier absent')
        elif tool=='workforce':
            result=campus_workforce.read(db,roles or {},permissions or {})
        elif tool=='economy':
            result=campus_economy.read(db,resources)
        elif tool=='infrastructure':
            result=campus_infrastructure.read(db,resources,registry)
        elif tool=='quality':
            result=campus_quality.read(db)
        elif tool=='incidents':
            # Persisted states only: never run incident eligibility or a recovery on read.
            counts=rows("SELECT mode,state,COUNT(*) AS count FROM missions WHERE state IN ('bloquée','en attente','interrompue') GROUP BY mode,state")
            result=[{'kind':'summary','counts':counts,'recovery_policy':incidents.LIMIT,
                     'recovery_count':db.execute("SELECT COUNT(*) FROM incident_recoveries").fetchone()[0]}]
            for r in rows("""SELECT m.id,m.title,m.mode,m.state,m.created,m.error,
                (SELECT COUNT(*) FROM requests q WHERE q.mission=m.id AND q.state='en attente') AS pending,
                (SELECT COUNT(*) FROM ledger l WHERE l.mission=m.id AND l.state='à rapprocher' AND l.actual IS NULL) AS unreconciled
                FROM missions m WHERE m.state IN ('bloquée','en attente','interrompue')
                ORDER BY m.id DESC LIMIT 50"""):
                diagnostic=incidents.classify(r['state'],r.pop('error'),r.pop('pending'),r.pop('unreconciled'))
                result.append({'kind':'mission',**r,**diagnostic})
            for r in rows("""SELECT campaign,mission,task,ledger,diagnostic,created
                FROM incident_recoveries ORDER BY created DESC,campaign DESC LIMIT 50"""):
                # A historical recovery is not proof that the mission completed.
                r['diagnostic']=r['diagnostic'] if r['diagnostic'] in incidents.TRANSIENT else 'Diagnostic hors liste'
                result.append({'kind':'recovery',**r})
        elif tool=='missions':
            result=rows("SELECT id,title,mode,state,created FROM missions ORDER BY id DESC LIMIT 100")
        elif tool=='work':
            result=rows("""SELECT t.id,t.mission,t.agent,t.state,t.created,m.mode,substr(t.goal,1,500) AS goal
                FROM tasks t JOIN missions m ON m.id=t.mission ORDER BY t.id DESC LIMIT 100""")
        elif tool=='files':
            result=rows("""SELECT a.id,a.mission,a.name,a.version,a.agent,a.created,m.mode,
                length(CAST(a.content AS BLOB)) AS bytes FROM artifacts a JOIN missions m ON m.id=a.mission
                ORDER BY a.id DESC LIMIT 100""")
        elif tool=='artifact':
            result=rows("""SELECT a.id,a.name,a.version,a.agent,a.mission,m.mode,
                length(CAST(a.content AS BLOB)) AS bytes,
                CASE WHEN length(CAST(a.content AS BLOB))<=? THEN a.content ELSE NULL END AS content
                FROM artifacts a JOIN missions m ON m.id=a.mission WHERE a.id=?""",(MAX_ARTIFACT_BYTES,ident))
            if not result: raise Missing('Livrable absent')
            if result[0]['content'] is None: raise TooLarge('Fichier trop volumineux ou sans contenu')
        elif tool=='memory':
            # Literal substring, no wildcard interpretation, bounded most recent matches.
            result=rows("""SELECT r.id,r.mission,r.agent,r.created,m.mode,m.title,
                substr(r.report,1,400) AS excerpt FROM reports r JOIN missions m ON m.id=r.mission
                WHERE instr(lower(COALESCE(r.report,'')),lower(?))>0
                   OR instr(lower(COALESCE(m.title,'')),lower(?))>0
                   OR instr(lower(COALESCE(r.agent,'')),lower(?))>0
                ORDER BY r.id DESC LIMIT 50""",(term,term,term))
        elif tool=='report':
            result=rows("""SELECT r.id,r.mission,r.agent,r.created,m.mode,m.title,
                length(CAST(r.report AS BLOB)) AS bytes,
                CASE WHEN length(CAST(r.report AS BLOB))<=? THEN r.report ELSE NULL END AS content
                FROM reports r JOIN missions m ON m.id=r.mission WHERE r.id=?""",(MAX_REPORT_BYTES,ident))
            if not result: raise Missing('Rapport absent')
            if result[0]['content'] is None: raise TooLarge('Rapport trop volumineux ou sans contenu')
            try:
                value=json.loads(result[0]['content'])
                if isinstance(value,dict) and isinstance(value.get('rapport'),str):
                    result[0]['content']=value['rapport']
            except (ValueError,TypeError): pass
        elif tool=='finance':
            result=rows("""SELECT COALESCE(NULLIF(l.agent,''),'Non attribué') AS agent,
                COALESCE(m.mode,'inconnu') AS mode, COUNT(*) AS calls,
                COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) AS committed_micro_usd,
                COALESCE(SUM(COALESCE(l.actual,0)),0) AS measured_micro_usd,
                COALESCE(SUM(CASE WHEN l.actual IS NULL THEN COALESCE(l.reserved,0) ELSE 0 END),0) AS unmeasured_micro_usd
                FROM ledger l LEFT JOIN missions m ON m.id=l.mission GROUP BY 1,2 ORDER BY 4 DESC,1,2 LIMIT 100""")
        elif tool=='owner':
            if resources is None:raise BadQuery('Ressources indisponibles')
            # No synchronization, planning, provider checks or mutation during dashboard reads.
            used=db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved,0)),0) FROM ledger").fetchone()[0]
            measured=db.execute("SELECT COALESCE(SUM(COALESCE(actual,0)),0) FROM ledger").fetchone()[0]
            searches=db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
            pending=db.execute("SELECT COUNT(*) FROM requests WHERE state='en attente'").fetchone()[0]
            active={
                'missions':rows("SELECT id,title,mode,state FROM missions WHERE state='en cours' ORDER BY id DESC LIMIT 10"),
                'campaigns':rows("SELECT id,goal,state,budget FROM campaigns WHERE state='actif' ORDER BY id DESC LIMIT 10"),
                'plans':rows("SELECT id,state,budget FROM enterprise_plans WHERE state='active' ORDER BY id DESC LIMIT 10"),
                'periods':rows("SELECT id,state,cadence,expires,total_budget FROM periodic_grants WHERE state='active' ORDER BY id DESC LIMIT 10"),
            }
            # Exact totals are independent of the ten-row detail cap.
            active_counts={
                'missions':db.execute("SELECT COUNT(*) FROM missions WHERE state='en cours'").fetchone()[0],
                'campaigns':db.execute("SELECT COUNT(*) FROM campaigns WHERE state='actif'").fetchone()[0],
                'plans':db.execute("SELECT COUNT(*) FROM enterprise_plans WHERE state='active'").fetchone()[0],
                'periods':db.execute("SELECT COUNT(*) FROM periodic_grants WHERE state='active'").fetchone()[0],
            }
            mission_counts=rows("SELECT mode,state,COUNT(*) AS count FROM missions GROUP BY mode,state ORDER BY mode,state")
            attention=rows("""SELECT id,substr(title,1,300) AS title,mode,state FROM missions
                WHERE state IN ('bloquée','en attente','interrompue') ORDER BY id DESC LIMIT 10""")
            attention_count=db.execute("SELECT COUNT(*) FROM missions WHERE state IN ('bloquée','en attente','interrompue')").fetchone()[0]
            pending_decisions=rows("""SELECT r.id,r.mission,m.mode,m.state AS mission_state,
                substr(m.title,1,300) AS title,r.task IS NOT NULL AND m.state='en attente' AS may_resume
                FROM requests r JOIN missions m ON m.id=r.mission WHERE r.state='en attente'
                ORDER BY r.id DESC LIMIT 10""")
            result=[{'kind':'resources','budget':resources['budget'],'committed':used,'measured':measured,
                'unmeasured':used-measured,'remaining':max(0,resources['budget']-used),
                'over_budget':used>resources['budget'],'search_limit':resources['search_limit'],'searches':searches,
                'mission_budget':resources['mission_budget'],'mission_calls':resources['mission_calls'],
                'openai_configured':resources['openai_configured'],'brave_configured':resources['brave_configured'],
                'sandbox_enabled':resources['sandbox_enabled'],'pending':pending,
                'configured_agents':len(roles or {}),'active':active,'active_counts':active_counts,
                'mission_counts':mission_counts,'attention':attention,'attention_count':attention_count,
                'pending_decisions':pending_decisions,'detail_limit':10}]
        elif tool=='decisions':
            result=rows("""SELECT r.id,r.mission,r.state,r.task,m.title,m.mode,m.state AS mission_state,
                CASE WHEN length(CAST(r.body AS BLOB))<=32768 THEN r.body ELSE NULL END AS body
                FROM requests r JOIN missions m ON m.id=r.mission
                ORDER BY CASE WHEN r.state='en attente' THEN 0 ELSE 1 END,r.id DESC LIMIT 100""")
            for r in result:
                try:
                    data=json.loads(r.pop('body') or '{}')
                    if not isinstance(data,dict):data={}
                except (ValueError,TypeError):data={}
                for k in ('objet','justification','cout_estime','risques'):
                    val=data.get(k)
                    r[k]=val[:1500] if isinstance(val,str) else None
                r['may_resume']=r['task'] is not None and r['mission_state']=='en attente'
        elif tool=='home':
            # Each category has its own limit. Status is persisted, not a health probe.
            result=[]
            for r in rows("""SELECT c.id,c.goal,c.state,c.budget,c.max_missions,c.search_cap,c.created,
                substr(c.reason,1,500) AS reason,
                (SELECT COUNT(*) FROM campaign_missions cm WHERE cm.campaign=c.id) AS missions,
                (SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) FROM ledger l
                 JOIN campaign_missions cm ON cm.mission=l.mission WHERE cm.campaign=c.id) AS committed
                FROM campaigns c ORDER BY CASE WHEN c.state='actif' THEN 0 ELSE 1 END,c.id DESC LIMIT 15"""):
                linked=db.execute('SELECT plan FROM enterprise_plan_queue WHERE campaign=?',(r['id'],)).fetchone()
                grant=periodic.linked_campaign(db,r['id'])
                searched=autopilot.searches(db,r['id'])
                result.append({'kind':'campaign',**r,'searches':searched,
                    'remaining':max(0,r['budget']-r['committed']),
                    'search_remaining':max(0,r['search_cap']-searched),
                    'plan_id':linked['plan'] if linked else None,
                    'grant_id':grant['grant_id'] if grant else None})
            for r in rows("""SELECT p.id,p.state,p.budget,p.per_campaign,p.max_campaigns,p.search_cap,p.created,
                substr(p.reason,1,500) AS reason,
                (SELECT COUNT(*) FROM enterprise_plan_queue q WHERE q.plan=p.id) AS campaigns,
                (SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) FROM ledger l
                 JOIN campaign_missions cm ON cm.mission=l.mission
                 JOIN enterprise_plan_queue q ON q.campaign=cm.campaign WHERE q.plan=p.id) AS committed
                FROM enterprise_plans p ORDER BY CASE WHEN p.state='active' THEN 0 ELSE 1 END,p.id DESC LIMIT 15"""):
                grant=periodic.linked_plan(db,r['id'])
                spent,searched=planner.totals(db,r['id'])
                result.append({'kind':'plan',**r,'committed':spent,'searches':searched,
                    'remaining':max(0,r['budget']-spent),
                    'search_remaining':max(0,r['search_cap']-searched),
                    'grant_id':grant['grant_id'] if grant else None})
            now=periodic.now()
            for r in rows("""SELECT g.id,g.cadence,g.periods,g.state,g.starts,g.expires,g.last_seen,g.total_budget,
                g.period_budget,g.per_campaign,g.total_search,g.period_search,g.max_campaigns,g.explore,substr(g.reason,1,500) AS reason,
                (SELECT COUNT(*) FROM periodic_slots s WHERE s.grant_id=g.id) AS slots
                FROM periodic_grants g ORDER BY CASE WHEN g.state IN ('active','suspended') THEN 0 ELSE 1 END,g.id DESC LIMIT 15"""):
                slots=periodic.slots(db,r['id'])
                spent=sum(x['spent'] for x in slots);searched=sum(x['searches'] for x in slots)
                window=(r['state']=='active' and max(r['starts'],r['last_seen'])<=now<r['expires'])
                result.append({'kind':'periodic',**{k:v for k,v in r.items() if k!='last_seen'},
                    'committed':spent,'searches':searched,'remaining':max(0,r['total_budget']-spent),
                    'search_remaining':max(0,r['total_search']-searched),'within_grant_window':window,
                    'slot_details':[{k:x[k] for k in ('slot','plan','state','starts','expires','budget','spent','search_cap','searches')} for x in slots]})
        elif tool=='portfolio':
            result=rows("""SELECT p.id,p.title,p.state,p.opportunity,p.created,
                (SELECT COUNT(*) FROM project_missions pm WHERE pm.project=p.id) AS missions,
                (SELECT COUNT(*) FROM artifacts a JOIN project_missions pm ON pm.mission=a.mission WHERE pm.project=p.id) AS artifacts,
                (SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) FROM ledger l
                 JOIN project_missions pm ON pm.mission=l.mission WHERE pm.project=p.id) AS committed
                FROM projects p ORDER BY p.id DESC LIMIT 100""")
        elif tool=='laboratory':
            result=rows("""SELECT r.id,r.artifact,r.campaign,r.profile,r.revision,r.size,r.status,r.created,
                a.name,a.version,m.mode
                FROM laboratory_runs r JOIN artifacts a ON a.id=r.artifact
                JOIN missions m ON m.id=a.mission ORDER BY r.id DESC LIMIT 100""")
        elif tool=='tools':
            policies={r['capability']:r for r in rows("""SELECT capability,enabled,max_calls,budget
                FROM connector_policies""")}
            result=[]
            for key,cap in sorted((registry or {}).items()):
                policy=policies.get(key)
                stats=rows("""SELECT COUNT(*) AS calls,COALESCE(SUM(reserved),0) AS reserved
                    FROM connector_runs WHERE capability=?""",(key,))[0]
                result.append({'kind':'capability','id':key,'label':cap['label'],'provider':cap['provider'],
                    'implemented':bool(cap['available']),'risk':cap['risk'],
                    'enabled':bool(policy and policy['enabled']),
                    'policy_present':policy is not None,'max_calls':policy['max_calls'] if policy else None,
                    'budget':policy['budget'] if policy else None,**stats})
            for r in rows("""SELECT id,capability,actor,state,reserved,created,finished
                FROM connector_runs ORDER BY id DESC LIMIT 50"""):
                result.append({'kind':'run',**r})
        elif tool in ('agents','goals'):
            # Configuration is a read-only projection of the engine definitions, never the API keys.
            xp={r['agent']:r['xp'] for r in rows("SELECT agent,COALESCE(SUM(xp),0) AS xp FROM rewards GROUP BY agent")}
            task_counts=rows("""SELECT t.agent,m.mode,COUNT(*) AS count FROM tasks t
                JOIN missions m ON m.id=t.mission GROUP BY t.agent,m.mode""")
            result=[{'id':aid,'role':role,'permissions':sorted((permissions or {}).get(aid,())),
                'xp':xp.get(aid,0),'task_counts':{r['mode']:r['count'] for r in task_counts if r['agent']==aid}}
                for aid,role in sorted((roles or {}).items())]
        else:
            result=rows("""SELECT o.id,o.mission,o.title,o.status,substr(o.body,1,1200) AS body,
                substr(o.next_test,1,600) AS next_test,o.created,m.mode FROM opportunities o
                JOIN missions m ON m.id=o.mission ORDER BY o.id DESC LIMIT 100""")
        return {'schema':'aes.campus.tool.v1','tool':tool,'read_only':True,'rows':result,
            'limit':51+len(roles or {}) if tool=='workforce' else 31 if tool=='economy' else 1+len(registry or {}) if tool=='infrastructure' else 101 if tool=='incidents' else 50 if tool=='memory' else 1 if tool in ('artifact','report') or tool in campus_commercial.DETAILS else 30 if tool=='marketing' else 81 if tool=='business' else 1 if tool=='owner' else 45 if tool=='home' else 50+len(registry or {}) if tool=='tools' else 100}
    finally:
        db.close()
