"""Budget fitting policy; caller owns the database transaction and cost ledger."""

def fit(c,mid,stage,agent,body,pi,po,cfg,used,campaign,*,costs,estimate,dumps):
    requested=body['max_output_tokens']
    spent,count=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()
    if count>=cfg['call_limit']:raise RuntimeError('Plafond des appels IA de mission atteint.')
    limits={'global':max(0,cfg['budget']-used),'mission':max(0,cfg['mission_budget']-spent),
            'campaign':max(0,campaign['budget']-costs(c,campaign['id']))}
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
        (mid,stage,agent,requested,preferred,chosen,req,floor,reserve,available,dumps(limits),decision))
    if chosen is None:
        why={'campaign':'Enveloppe Autopilote','mission':'Budget de mission','global':'Budget logiciel'}[min(limits,key=limits.get)]
        return None,None,f'{why} insuffisant(e) : réservation minimale {floor/1e6:.6f} USD, disponible {available/1e6:.6f} USD; aucun appel envoyé.'
    return chosen,reserve,None
