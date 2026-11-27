"""D03/D07: read-only local projection, including persisted task and delegation state."""
import sqlite3
from pathlib import Path
from infrastructure.database import read_snapshot
from datetime import datetime, timezone

BUILDINGS = {
    'ATLAS': ('ATLAS',), 'ORION': ('ORION',), 'NEXUS': ('NEXUS',),
    'MIDAS': ('MIDAS',), 'HERMES': ('HERMES',), 'SENTINEL': ('SENTINEL',),
    'CORE': ('MNEMOS', 'PROMETHEUS'),
}

def snapshot(path, agents, budget, version):
    # mode=ro prevents creating a missing database or writing existing data.
    with read_snapshot(path) as db:
        def rows(sql, params=()):
            return [dict(r) for r in db.execute(sql, params)]
        missions=rows("SELECT id,title,mode,state,created FROM missions ORDER BY id DESC LIMIT 30")
        tasks=rows("""SELECT t.id,t.mission,t.agent,t.state,t.created,m.mode
            FROM tasks t JOIN missions m ON m.id=t.mission ORDER BY t.id DESC LIMIT 60""")
        active=rows("""SELECT t.agent,m.mode,COUNT(*) AS count
            FROM tasks t JOIN missions m ON m.id=t.mission
            WHERE m.state='en cours' AND t.state='en cours'
            GROUP BY t.agent,m.mode""")
        # A dynamic task can remain "prête" while the engine selects it (missions.step).
        # Selection is not proof of a running provider call or physical occupancy.
        activity=rows("""SELECT agent,mode,activity_state,COUNT(*) AS count FROM (
            SELECT t.agent,m.mode,CASE
                WHEN m.state='bloquée' OR t.state='bloquée' THEN 'blocked'
                WHEN m.state='en attente' OR t.state='en attente' THEN 'waiting'
                WHEN t.state='en cours' THEN 'running_recorded'
                WHEN m.step=t.id AND t.state='prête' AND NOT EXISTS(
                    SELECT 1 FROM tasks child WHERE child.parent=t.id AND child.mission=t.mission AND child.state!='terminée')
                    THEN 'selected'
                ELSE 'queued' END AS activity_state
            FROM tasks t JOIN missions m ON m.id=t.mission
            WHERE m.engine='dynamic' AND m.state IN ('en cours','en attente','bloquée')
              AND t.state IN ('prête','en cours','en attente','bloquée')
            ) GROUP BY agent,mode,activity_state""")
        delegations=rows("""SELECT child.id AS id,child.mission,parent.agent AS from_agent,
            child.agent AS to_agent,child.state,child.created,m.mode,m.state AS mission_state
            FROM tasks child JOIN tasks parent ON parent.id=child.parent AND parent.mission=child.mission
            JOIN missions m ON m.id=child.mission
            WHERE m.engine='dynamic' AND parent.agent!=child.agent
            ORDER BY child.id DESC LIMIT 30""")
        events=rows("""SELECT e.id,e.mission,e.agent,e.action,e.ok,e.created,m.mode
            FROM events e JOIN missions m ON m.id=e.mission ORDER BY e.id DESC LIMIT 30""")
        artifacts=rows("""SELECT a.id,a.mission,a.agent,a.name,a.version,a.created,m.mode
            FROM artifacts a JOIN missions m ON m.id=a.mission ORDER BY a.id DESC LIMIT 30""")
        mission_counts=rows("SELECT mode,state,COUNT(*) AS count FROM missions GROUP BY mode,state")
        used=db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved,0)),0) FROM ledger").fetchone()[0]
        waiting=db.execute("SELECT COUNT(*) FROM requests WHERE state='en attente'").fetchone()[0]
        attention=rows("SELECT id,mode,state FROM missions WHERE state IN ('bloquée','en attente') ORDER BY id DESC LIMIT 20")
        # Financial indicators are deliberately not inferred from TEST receipts,
        # API reservations or an incomplete accounting ledger. No provider calls.
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('business_receipts','campaigns')")}
        declared=None
        if 'business_receipts' in tables:
            receipt=db.execute("""SELECT COUNT(*) AS count,
                COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END),0) AS net
                FROM business_receipts WHERE mode='owner_declared_live' AND kind IN ('payment','refund')""").fetchone()
            declared={'count':receipt['count'],'net_cents':receipt['net']}
        campaigns=None
        if 'campaigns' in tables:
            campaign=db.execute("SELECT COUNT(*) AS total,COALESCE(SUM(CASE WHEN state='actif' THEN 1 ELSE 0 END),0) AS active FROM campaigns").fetchone()
            campaigns={'active':campaign['active'],'total':campaign['total']}
        kpi={'currency':'EUR','verified_revenue_cents':None,'net_profit_cents':None,
             'net_margin_percent':None,'declared_receipts_all_time':declared,
             'campaigns':campaigns,'api_today_micro_usd':None}
        return {'schema':'aes.campus.read.v1','version':version,'source':'local_sqlite',
            'generated_at':datetime.now(timezone.utc).isoformat(),'read_only':True,
            'activity':{'schema_version':1,'delegations':delegations,'delegation_limit':30},
            'buildings':[{'id':bid,'agents':[{'id':aid,'role':agents[aid],
                'active_tasks_by_mode':{r['mode']:r['count'] for r in active if r['agent']==aid},
                'activity':[{'mode':r['mode'],'state':r['activity_state'],'count':r['count']} for r in activity if r['agent']==aid]}
                for aid in ids if aid in agents]} for bid,ids in BUILDINGS.items()],
            'unmapped_agents':[{'id':a,'role':role} for a,role in agents.items()
                if not any(a in ids for ids in BUILDINGS.values())],
            'budget':{'currency':'USD','limit_micro_usd':budget,'committed_estimate_micro_usd':used},
            'enterprise_kpi':kpi,
            'pending_requests':waiting,'mission_counts':mission_counts,'attention_missions':attention,
            'missions':missions,'tasks':tasks,'events':events,'artifacts':artifacts}
