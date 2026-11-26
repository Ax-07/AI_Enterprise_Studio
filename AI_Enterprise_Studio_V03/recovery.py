"""Explicit, bounded administrative recovery of an exhausted Shopify audit.
Never fabricate an agent report, reset counters or call a provider.
"""
import hashlib,json
import verification

def candidate(c,mid,cfg):
    mission=c.execute("SELECT * FROM missions WHERE id=? AND mode='cloud' AND engine='dynamic' AND state='bloquée'",(mid,)).fetchone()
    if not mission: return None
    if c.execute("SELECT 1 FROM requests WHERE mission=? AND state='en attente'",(mid,)).fetchone(): return None
    t=c.execute("""SELECT * FROM tasks t WHERE mission=? AND state='prête'
        AND NOT EXISTS(SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    if not t or t['agent']!='SENTINEL' or t['turns']<cfg.get('turn_limit',10) or mission['error']!='Plafond de tours atteint pour la tâche #'+str(t['id']): return None
    # Restrict this recovery to an exact known four-case contract. Not a generic audit approval.
    artifact=c.execute("SELECT * FROM artifacts WHERE mission=? AND agent='NEXUS' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
    if not artifact or not artifact['name'].lower().endswith('.html'): return None
    v=c.execute('SELECT * FROM verification_results WHERE artifact=? ORDER BY id DESC LIMIT 1',(artifact['id'],)).fetchone()
    if not v or v['mission']!=mid or v['agent']!='SENTINEL': return None
    try:
        spec=json.loads(v['spec']); result=json.loads(v['result'])
        if spec!=verification.shopify_spec(): return None
        sha=hashlib.sha256(artifact['content'].encode('utf-8')).hexdigest()
        if result.get('sha256')!=sha or result.get('kind')!='html' or result.get('status')!='passed': return None
        checks=result['checks']; names=[x['name'] for x in spec['cases']]
        if [x['name'] for x in checks]!=names or not all(x.get('passed') is True for x in checks): return None
        # Require a tool event from THIS task, not another auditor or owner proof.
        event=None
        for e in c.execute("SELECT id,result FROM events WHERE mission=? AND task=? AND agent='SENTINEL' AND action='test_file' AND ok=1 ORDER BY id DESC",(mid,t['id'])):
            observed=json.loads(e['result'])
            if observed.get('verification_id')==v['id'] and observed.get('fichier')==artifact['id'] and all(observed.get(k)==result.get(k) for k in ('sha256','status','checks','kind')):
                event=e['id'];break
        if event is None:return None
    except (KeyError,ValueError,TypeError,AttributeError): return None
    return {'mission':mid,'task':t['id'],'artifact':artifact['id'],'name':artifact['name'],'version':artifact['version'],
            'proof':v['id'],'event':event,'sha256':sha,'checks':names,'turns':t['turns']}

def close(c,mid,task,proof,cfg):
    # Caller holds a SQLite write transaction. Recompute eligibility inside it.
    if any(type(x) is not int or not 0<x<=9007199254740991 for x in (mid,task,proof)): raise ValueError('Identifiants invalides')
    if c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone(): raise ValueError('Une mission est déjà en cours')
    p=candidate(c,mid,cfg)
    if not p or (p['task'],p['proof'])!=(task,proof): raise ValueError('Clôture impossible : preuve ou état modifié; actualiser le diagnostic')
    report=(f"SYNTHÈSE TECHNIQUE DU MOTEUR — clôture administrative partielle, confirmée par le propriétaire. "
            f"SENTINEL, tâche #{task}, a exécuté test_file (événement #{p['event']}) : preuve #{proof}, "
            f"fichier #{p['artifact']} {p['name']} V{p['version']}, SHA-256 {p['sha256']}. "
            "Résultat observé : 4 cas de test sur 4 réussis. Cas : "+'; '.join(p['checks'])+". "
            f"Le plafond de {p['turns']} tours est atteint; aucun rapport de conclusion rédigé par SENTINEL. "
            "Cette clôture conserve la preuve, ne certifie pas les autres critères de la tâche (notamment repli sur date, langues et autres cas non couverts), "
            "ni les exports réels, la sécurité générale ou la validité commerciale. ATLAS doit distinguer ces limites dans sa conclusion et prévoir les tests manquants si nécessaires. Aucun appel IA pour cette clôture.")
    c.execute("UPDATE tasks SET state='terminée',result=? WHERE id=?",(report,task))
    seq=c.execute('SELECT COALESCE(MAX(step),-1)+1 FROM reports WHERE mission=?',(mid,)).fetchone()[0]
    body={'rapport':report,'requetes':[],'demandes':[],'provenance':'systeme_cloture_partielle','task':task,'proof':proof,'event':p['event']}
    c.execute('INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,?,?,?,?)',(mid,seq,'SYSTEME',json.dumps(body,ensure_ascii=False),'[]'))
    c.execute("INSERT INTO events(mission,task,agent,action,args,result,ok) VALUES(?,?,'SYSTEME','close_audit',?,?,1)",(mid,task,json.dumps({'proof':proof,'confirm':True}),json.dumps({'status':'clôture partielle','rapport_systeme':seq,'proof':proof})))
    # Do not start worker. Separate user confirmation needed for any Cloud resume.
    c.execute("UPDATE missions SET state='prête',error='Audit clôturé partiellement par le moteur; conclusion ATLAS à reprendre.' WHERE id=?",(mid,))
    return {'id':mid,'task':task,'proof':proof,'status':'clôture partielle','paid_call':False}
