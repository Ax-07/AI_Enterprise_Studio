"""Read-only portfolio progression and selection policy.
Historical permissions, ordering and evidence checks are preserved.
"""

def next_step(c,pid,flags,*,project,latest,economic_hold,history,evidence,laboratory):
    p=project(c,pid)
    if not p or p['state']!='active':return None,'Activité suspendue ou archivée.'
    a=latest(c,pid)
    if not a:
        if economic_hold(c,p['opportunity']):return None,'Production suspendue : dernier scénario économique vérifié déficitaire ou sans marge. Préparation commerciale ou réévaluation requise.'
        if flags['production'] and p['opportunity'] is not None and not history(c,pid,'create'):
            o=c.execute('SELECT id,title,next_test FROM opportunities WHERE id=?',(p['opportunity'],)).fetchone()
            if o:return ('create',None,dict(o)),'Premier prototype et expérience interne.'
        return None,'Aucun livrable exploitable; production non autorisée ou déjà tentée.'
    aid=a['id'];proofs=evidence(c,a)
    if laboratory.supports(a):
        lab=laboratory.canonical(c,a)
        if not lab or lab['status']=='unavailable':
            if flags['tests']:return ('laboratory',aid,None),'Banc d’essai indépendant de 300 lignes, sans appel IA.'
            return None,'Banc d’essai requis mais non autorisé.'
        if lab['status']!='passed':return None,'Banc d’essai non réussi; diagnostic et correction ciblée nécessaires.'
    independent=[v for v in proofs if v['agent']=='SENTINEL']
    if any(v['status']=='failed' for v in independent):
        if flags['production'] and not history(c,pid,'improve',aid):
            return ('improve',aid,None),'Échec fonctionnel observé sur cette version.'
        return None,'Échec indépendant non résolu; examen requis.'
    if not any(v['status']=='passed' for v in independent):
        if flags['tests'] and a['name'].lower().endswith(('.html','.csv','.json')) and not history(c,pid,'functional',aid):
            return ('functional',aid,None),'Aucune preuve indépendante réussie sur cette version.'
        return None,'Audit indépendant manquant ou déjà tenté; examen requis.'
    if flags['market'] and not history(c,pid,'market',aid):
        return ('market',aid,None),'Étude commerciale interne, sans validation de demande.'
    return None,'Étapes internes déjà étudiées ou non autorisées; preuves commerciales encore à établir.'


def recommend(c,flags,*,next_step):
    # Prioritize a concrete next step; least recently studied first. No invented score.
    candidates=[]
    for p in c.execute("SELECT * FROM projects WHERE state='active' ORDER BY id"):
        step,reason=next_step(c,p['id'],flags)
        if step:
            last=c.execute('SELECT COALESCE(MAX(mission),0) FROM project_missions WHERE project=?',(p['id'],)).fetchone()[0]
            candidates.append((last,p['id'],step,reason))
    if not candidates:return None
    _,pid,step,reason=min(candidates,key=lambda x:(x[0],x[1]))
    return {'id':pid,'kind':step[0],'reason':reason}


def select(c,requested,flags,*,recommend,project,next_step):
    if requested=='explore':
        if not flags['research']:raise ValueError('Exploration non autorisée')
        return None,'explore'
    if requested=='auto':
        rec=recommend(c,flags)
        if rec:return rec['id'],'project'
        if flags['research']:return None,'explore'
        raise ValueError('Aucune activité avec une prochaine étape autorisée')
    if type(requested) is not int or not 1<=requested<=9007199254740991:raise ValueError('Activité invalide')
    p=project(c,requested)
    if not p or p['state']!='active':raise ValueError('Activité inactive ou inconnue')
    if not next_step(c,requested,flags)[0]:raise ValueError('Aucune prochaine étape autorisée pour cette activité')
    return requested,'project'
