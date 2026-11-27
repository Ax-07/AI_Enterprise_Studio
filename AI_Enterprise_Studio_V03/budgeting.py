"""Conservative fit of the actual outgoing output limit; no change to price or input bound."""
import math,json
from departments import ai_costs, budget_envelopes

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
    return budget_envelopes.fit(c,mid,stage,agent,body,pi,po,cfg,used,campaign,
                                costs=autopilot.costs,estimate=estimate,dumps=json.dumps)
def history(c,mid=None):
    q='SELECT * FROM budget_decisions';args=()
    if mid is not None:q+=' WHERE mission=?';args=(mid,)
    q+=' ORDER BY id DESC LIMIT 100'
    return [{**dict(x),'limits':json.loads(x['limits'])} for x in c.execute(q,args)]
