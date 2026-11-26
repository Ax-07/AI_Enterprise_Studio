"""D03: bounded, read-only local projection. No calls to agents or connectors."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

BUILDINGS = {
    'ATLAS': ('ATLAS',), 'ORION': ('ORION',), 'NEXUS': ('NEXUS',),
    'MIDAS': ('MIDAS',), 'HERMES': ('HERMES',), 'SENTINEL': ('SENTINEL',),
    'CORE': ('MNEMOS', 'PROMETHEUS'),
}

def snapshot(path, agents, budget, version):
    # mode=ro prevents creating a missing database or writing existing data.
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=3) as db:
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            def rows(sql, params=()):
                return [dict(r) for r in db.execute(sql, params)]
            missions=rows("SELECT id,title,mode,state,created FROM missions ORDER BY id DESC LIMIT 30")
            tasks=rows("""SELECT t.id,t.mission,t.agent,t.state,t.created,m.mode
                FROM tasks t JOIN missions m ON m.id=t.mission ORDER BY t.id DESC LIMIT 60""")
            active=rows("""SELECT t.agent,m.mode,COUNT(*) AS count
                FROM tasks t JOIN missions m ON m.id=t.mission
                WHERE m.state='en cours' AND t.state='en cours'
                GROUP BY t.agent,m.mode""")
            events=rows("""SELECT e.id,e.mission,e.agent,e.action,e.ok,e.created,m.mode
                FROM events e JOIN missions m ON m.id=e.mission ORDER BY e.id DESC LIMIT 30""")
            artifacts=rows("""SELECT a.id,a.mission,a.agent,a.name,a.version,a.created,m.mode
                FROM artifacts a JOIN missions m ON m.id=a.mission ORDER BY a.id DESC LIMIT 30""")
            mission_counts=rows("SELECT mode,state,COUNT(*) AS count FROM missions GROUP BY mode,state")
            used=db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved,0)),0) FROM ledger").fetchone()[0]
            waiting=db.execute("SELECT COUNT(*) FROM requests WHERE state='en attente'").fetchone()[0]
            return {'schema':'aes.campus.read.v1','version':version,'source':'local_sqlite',
                'generated_at':datetime.now(timezone.utc).isoformat(),'read_only':True,
                'buildings':[{'id':bid,'agents':[{'id':aid,'role':agents[aid],
                    'active_tasks_by_mode':{r['mode']:r['count'] for r in active if r['agent']==aid}}
                    for aid in ids if aid in agents]} for bid,ids in BUILDINGS.items()],
                'unmapped_agents':[{'id':a,'role':role} for a,role in agents.items()
                    if not any(a in ids for ids in BUILDINGS.values())],
                'budget':{'currency':'USD','limit_micro_usd':budget,'committed_estimate_micro_usd':used},
                'pending_requests':waiting,'mission_counts':mission_counts,
                'missions':missions,'tasks':tasks,'events':events,'artifacts':artifacts}
        finally:
            db.close()
