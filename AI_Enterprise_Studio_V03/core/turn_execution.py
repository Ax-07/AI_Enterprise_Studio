"""Internal action processing and event recording, after the legacy turn guards.

Preserve transaction boundaries, repeat detection, exception handling and XP policy.
The caller supplies the current legacy callbacks; this module grants no permission.
"""
 

def process_action(s,mid,t,v,cfg,mode,action_args,repeat_count,execute,log,agent_is_auditor):
    a=v['action']; ok=True
    compact=action_args(v)
    with s.db() as c: repeats=repeat_count(c,t['id'],v)
    if repeats>=2: raise RuntimeError('Action identique répétée trois fois; tâche #'+str(t['id'])+' ; outil '+a+' ; cible '+v['target'][:100])
    try: result=execute(s,t,v,cfg,mode)
    except (ValueError,ArithmeticError,SyntaxError,TypeError) as e: result={'erreur':str(e)[:400]};ok=False
    blocked=False
    with s.db() as c:
        eid=log(c,t,a,compact,result,ok)
        # Reward only objectively observed static checks by independent auditor; demo never earns XP.
        if mode=='cloud' and ok and agent_is_auditor(t) and a=='check_file' and result.get('valide') and not result.get('reference') and result['nom'].lower().endswith(('.py','.csv','.json')):
            previous=c.execute("SELECT 1 FROM rewards r JOIN events e ON e.id=r.event WHERE r.mission=? AND r.agent=? AND e.action='check_file' AND json_extract(e.result,'$.nom')=?",(mid,t['agent'],result['nom'])).fetchone()
            if not previous: c.execute('INSERT INTO rewards(mission,agent,event,xp,reason) VALUES(?,?,?,?,?)',(mid,t['agent'],eid,10,'Premier contrôle statique réussi par fichier; pas de validation commerciale'))
        if not ok:
            last=list(c.execute('SELECT ok FROM events WHERE task=? ORDER BY id DESC LIMIT 3',(t['id'],)))
            blocked=len(last)==3 and all(not r[0] for r in last)
    # Commit the failure event before raising; no lost third failure.
    if blocked:raise RuntimeError('Trois outils refusés/échoués de suite sur tâche #'+str(t['id']))
