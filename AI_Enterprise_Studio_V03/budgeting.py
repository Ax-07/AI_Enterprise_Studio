"""Conservative fit of the actual outgoing output limit; no change to price or input bound."""
import math,json
from departments import ai_costs

def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS budget_decisions(
        id INTEGER PRIMARY KEY,mission INTEGER NOT NULL REFERENCES missions(id),task INTEGER,agent TEXT NOT NULL,
        requested_tokens INTEGER NOT NULL,preferred_tokens INTEGER NOT NULL,chosen_tokens INTEGER,
        requested_reserve INTEGER NOT NULL,minimum_reserve INTEGER NOT NULL,chosen_reserve INTEGER,
        available INTEGER NOT NULL,limits TEXT NOT NULL,decision TEXT NOT NULL,
        created TEXT DEFAULT CURRENT_TIMESTAMP)""")
def estimate(body,pi,po,tokens):
    b={**body,'max_output_tokens':tokens}
    return ai_costs.reservation(b,pi,po,tokens,dumps=json.dumps,ceil=math.ceil)
def fit(c,mid,stage,agent,body,pi,po,cfg,used,campaign):
    import autopilot
    requested=body['max_output_tokens']
    spent,count=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()
    if count>=cfg['call_limit']:raise RuntimeError('Plafond des appels IA de mission atteint.')
    limits={'global':max(0,cfg['budget']-used),'mission':max(0,cfg['mission_budget']-spent),
            'campaign':max(0,campaign['budget']-autopilot.costs(c,campaign['id']))}
    available=min(limits.values())
    preferred=requested
    # A saved draft already exists: short follow-up by default, not a forced finish.
    if agent=='NEXUS' and requested==8192 and c.execute("SELECT 1 FROM events WHERE mission=? AND task=? AND action='write_file' AND ok=1",(mid,stage)).fetchone():
        preferred=2048
    # ATLAS coordinates short actions; keep the full corrective allowance on retry.
    if agent=='ATLAS' and requested==4096:preferred=2048
    minimum=min(preferred,1024)
    req=estimate(body,pi,po,requested);floor=estimate(body,pi,po,minimum)
    chosen=None;reserve=None
    if floor<=available:
        lo,hi=minimum,preferred
        while lo<hi:
            m=(lo+hi+1)//2
            if estimate(body,pi,po,m)<=available:lo=m
            else:hi=m-1
        chosen=lo;reserve=estimate(body,pi,po,chosen)
    decision='refused' if chosen is None else 'adapted' if chosen<requested else 'unchanged'
    c.execute("""INSERT INTO budget_decisions(mission,task,agent,requested_tokens,preferred_tokens,chosen_tokens,
        requested_reserve,minimum_reserve,chosen_reserve,available,limits,decision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mid,stage,agent,requested,preferred,chosen,req,floor,reserve,available,json.dumps(limits),decision))
    if chosen is None:
        why={'campaign':'Enveloppe Autopilote','mission':'Budget de mission','global':'Budget logiciel'}[min(limits,key=limits.get)]
        return None,None,f'{why} insuffisant(e) : réservation minimale {floor/1e6:.6f} USD, disponible {available/1e6:.6f} USD; aucun appel envoyé.'
    return chosen,reserve,None
def history(c,mid=None):
    q='SELECT * FROM budget_decisions';args=()
    if mid is not None:q+=' WHERE mission=?';args=(mid,)
    q+=' ORDER BY id DESC LIMIT 100'
    return [{**dict(x),'limits':json.loads(x['limits'])} for x in c.execute(q,args)]
