"""Internal coordination handlers, under moteur.execute's authorization and transaction.

No new permission, owner authorization, independent commit or external action.
Dependencies are supplied by the legacy facade at the point of use.
"""
import json


def execute_delegate(c,t,mid,target,text,detail,cfg,roles,add_task):
    if target=='ATLAS' or target not in roles: raise ValueError('Destinataire invalide')
    if c.execute('SELECT COUNT(*) FROM tasks WHERE mission=?',(mid,)).fetchone()[0]>=cfg['task_limit']: raise ValueError('Plafond de tâches atteint')
    if c.execute('SELECT 1 FROM tasks WHERE mission=? AND agent=? AND goal=?',(mid,target,text)).fetchone(): raise ValueError('Tâche identique déjà créée')
    tid=add_task(c,mid,target,text,detail,t['id']); return {'tache':tid,'agent':target}


def execute_request(c,t,mid,target,text,detail):
    if not target or not text.strip() or not detail.strip(): raise ValueError('Objet, justification, coûts et risques requis')
    if c.execute('SELECT COUNT(*) FROM requests WHERE mission=? AND task IS NOT NULL',(mid,)).fetchone()[0]>=4: raise ValueError('Plafond de demandes atteint')
    if c.execute('SELECT 1 FROM requests WHERE task=? AND body LIKE ?',(t['id'],'%'+target[:120]+'%')).fetchone(): raise ValueError('Demande déjà formulée, consulte le résultat de décision')
    d={'objet':target[:160],'justification':text[:4000],'cout_estime':'Aucun achat autorisé. '+detail[:1000],'risques':detail[:1000]}
    rid=c.execute('INSERT INTO requests(mission,body,task) VALUES(?,?,?)',(mid,json.dumps(d,ensure_ascii=False),t['id'])).lastrowid
    c.execute("UPDATE tasks SET state='en attente' WHERE id=?",(t['id'],));return {'demande':rid,'statut':'en attente','portée':'étude seulement; aucun accès ni paiement accordé'}


def execute_finish(c,t,mid,agent,text,cfg,mode,followup_mission,permitted,perms,memory_policy,memory_snapshot,documentary_first_search):
    if not text.strip(): raise ValueError('Rapport vide')
    if agent=='ATLAS' and not c.execute('SELECT 1 FROM tasks WHERE parent=?',(t['id'],)).fetchone(): raise ValueError('ATLAS doit déléguer au moins une tâche')
    if mode=='cloud' and followup_mission(c,mid):
        if agent=='ATLAS' and not c.execute("SELECT 1 FROM tasks WHERE mission=? AND agent='ORION' AND state='terminée'",(mid,)).fetchone():raise ValueError('Complément : déléguer ORION et attendre son rapport')
        if agent=='ORION' and t['turns']+1<cfg['turn_limit']:
            allowed,_=permitted(c,mid,agent,perms[agent])
            allowed=memory_policy(c,t,cfg,allowed,memory_snapshot(c,t))
            if documentary_first_search(c,t,allowed):raise ValueError('Complément : première recherche autorisée obligatoire')
    c.execute("UPDATE tasks SET state='terminée',result=? WHERE id=?",(text[:18000],t['id']))
    seq=c.execute('SELECT COALESCE(MAX(step),-1)+1 FROM reports WHERE mission=?',(mid,)).fetchone()[0]
    c.execute('INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,?,?,?,?)',(mid,seq,agent,json.dumps({'rapport':text,'requetes':[],'demandes':[]},ensure_ascii=False),'[]'))
    return {'tache':t['id'],'statut':'rapport déposé (non certifié)'}
