"""Read-only recorded task load and dependencies. No scheduling or competence inference."""
LIMIT="Charge enregistrée, pas une mesure de disponibilité, de présence, de compétence ou de temps de calcul. Une tâche sélectionnée ne prouve pas un appel en cours. Aucune délégation exécutée."
def read(db, roles, permissions):
    def rows(sql,args=()):
        return [dict(r) for r in db.execute(sql,args)]
    # Match the existing engine's runnable-task predicate; no provider or policy probe.
    counts=rows("""SELECT agent,mode,category,COUNT(*) AS count FROM (
        SELECT t.agent,m.mode,CASE
            WHEN m.state='bloquée' OR t.state='bloquée' THEN 'blocked'
            WHEN m.state='en attente' OR t.state='en attente' THEN 'waiting'
            WHEN EXISTS(SELECT 1 FROM tasks child WHERE child.parent=t.id AND child.state!='terminée') THEN 'dependency'
            WHEN t.state='en cours' THEN 'running_recorded'
            WHEN t.state='prête' AND m.step=t.id THEN 'selected'
            ELSE 'queued' END AS category
        FROM tasks t JOIN missions m ON m.id=t.mission
        WHERE m.engine='dynamic' AND m.state IN ('en cours','en attente','bloquée')
          AND t.state IN ('prête','en cours','en attente','bloquée')
        ) GROUP BY agent,mode,category ORDER BY agent,mode,category""")
    # Historical action outcomes are evidence of tool usage, not competence scores.
    # Only known action names are exposed; other historical actions are aggregated.
    known=set().union(*(set(x) for x in permissions.values()))
    actions=rows("""SELECT e.agent,m.mode,e.action,e.ok,COUNT(*) AS count
        FROM events e JOIN missions m ON m.id=e.mission
        WHERE m.engine='dynamic' GROUP BY e.agent,m.mode,e.action,e.ok""")
    evidence={}
    for r in actions:
        if r['agent'] not in roles:continue
        mode=r['mode'] if r['mode'] in ('cloud','demo') else 'other'
        action=r['action'] if r['action'] in known else 'other'
        key=(mode,action)
        bucket=evidence.setdefault(r['agent'],{}).setdefault(key,{'mode':mode,'action':action,'ok':0,'failed':0,'unknown':0})
        bucket['ok' if r['ok']==1 else 'failed' if r['ok']==0 else 'unknown']+=r['count']
    completed=rows("""SELECT t.agent,m.mode,COUNT(*) AS count FROM tasks t
        JOIN missions m ON m.id=t.mission WHERE m.engine='dynamic' AND t.state='terminée'
        GROUP BY t.agent,m.mode ORDER BY t.agent,m.mode""")
    total=db.execute("""SELECT COUNT(*) FROM tasks child JOIN tasks parent
        ON parent.id=child.parent AND parent.mission=child.mission
        JOIN missions m ON m.id=child.mission
        WHERE m.engine='dynamic' AND parent.agent!=child.agent""").fetchone()[0]
    edges=rows("""SELECT child.id,child.mission,child.parent,parent.agent AS from_agent,
        child.agent AS to_agent,child.state,m.state AS mission_state,m.mode
        FROM tasks child JOIN tasks parent ON parent.id=child.parent AND parent.mission=child.mission
        JOIN missions m ON m.id=child.mission
        WHERE m.engine='dynamic' AND parent.agent!=child.agent
        ORDER BY child.id DESC LIMIT 50""")
    out=[{'kind':'summary','limit':LIMIT,'configured':len(roles),
        'unresolved':sum(r['count'] for r in counts),
        'unmapped_tasks':sum(r['count'] for r in counts if r['agent'] not in roles),
        'delegation_count':total,'delegations_displayed':len(edges)}]
    for aid,role in sorted(roles.items()):
        out.append({'kind':'agent','id':aid,'role':role,'permissions':sorted(permissions.get(aid,())),
            'load':[{k:v for k,v in r.items() if k!='agent'} for r in counts if r['agent']==aid],
            'completed_tasks':[{'mode':r['mode'] if r['mode'] in ('cloud','demo') else 'other','count':r['count']} for r in completed if r['agent']==aid],
            'tool_evidence':[v for k,v in sorted(evidence.get(aid,{}).items())],
            'competence_rating':None})
    for r in edges:
        # Do not expose arbitrary identifiers from corrupt or unknown agent rows as roles.
        for key in ('from_agent','to_agent'):
            if r[key] not in roles:r[key]='non configuré'
        out.append({'kind':'delegation',**r})
    return out
