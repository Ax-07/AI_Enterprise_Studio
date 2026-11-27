"""Internal execution handlers for connector, verification and research actions.

Call only after moteur.execute has applied permanent permissions and operational
guards. All existing per-action checks and transaction boundaries are retained.
Dependencies are passed at call time; no business module or transport imported.
"""
import json


def execute_connector(s,t,mid,agent,target,text,detail,mode,invoke):
    if mode!='cloud' or detail:raise ValueError('Connecteur Cloud, detail vide requis')
    return invoke(s,target,text,mid,t['id'],agent)


def execute_test_file(s,mid,agent,target,text,cfg,mode,resolve_artifact,verification_spec,record_verification):
    if mode!='cloud': raise ValueError('Les tests agents sont réservés aux missions Cloud; simulation standard inchangée')
    with s.db() as c:
        if c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0]!='en cours': raise ValueError('Mission arrêtée')
        row,_=resolve_artifact(c,mid,target)
        if not row: raise ValueError('Fichier absent')
        row=dict(row)
        if c.execute('SELECT COUNT(*) FROM verification_results WHERE mission=? AND agent IN (\'NEXUS\',\'SENTINEL\')',(mid,)).fetchone()[0]>=8: raise ValueError('Plafond de tests de mission atteint')
        spec=verification_spec(c,mid,row,text)
    return record_verification(s,row,mid,agent,spec,cfg)


def execute_search(s,mid,text,cfg,mode):
    if mode=='demo': raise ValueError('Réseau interdit en simulation')
    if not cfg['brave']: raise ValueError('Clé Brave manquante')
    q=text.strip()
    if not 1<=len(q)<=200: raise ValueError('Requête de 1 à 200 caractères')
    with s.db() as c:
        old=c.execute("SELECT result FROM searches WHERE mission=? AND query=? AND status='reçue' ORDER BY id DESC LIMIT 1",(mid,q)).fetchone()
        if old: return {'cache':True,'extraits_non_vérifiés':json.loads(old['result'])}
        if c.execute('SELECT COUNT(*) FROM searches').fetchone()[0]>=cfg['limit']: raise ValueError('Plafond Brave cumulatif atteint')
        if c.execute('SELECT COUNT(*) FROM searches WHERE mission=?',(mid,)).fetchone()[0]>=cfg['mission_search_limit']: raise ValueError('Plafond Brave de mission atteint')
    rows=s.search(mid,[q],cfg)
    return {'extraits_non_vérifiés':rows,'note':'Résultats ou liste vide; vérifier les pages officielles. Tentative décomptée.'}


def execute_read(s,mid,target,cfg,mode,fetch_page,classify_failure):
    if mode=='demo': raise ValueError('Réseau interdit en simulation')
    with s.db() as c:
        allowed={x.get('url') for row in c.execute("SELECT result FROM searches WHERE mission=? AND status='reçue'",(mid,)) for x in json.loads(row['result'])}
        if target not in allowed: raise ValueError('URL non issue des résultats Brave de cette mission')
        old=c.execute("SELECT id,content FROM fetched WHERE mission=? AND url=? AND state='reçue' ORDER BY id DESC LIMIT 1",(mid,target)).fetchone()
        if old: return {**json.loads(old['content']),'page_ref':old['id'],'cache':True}
        if c.execute("SELECT 1 FROM fetched WHERE mission=? AND url=? AND state='échec'",(mid,target)).fetchone():raise ValueError('Lecture déjà échouée dans cette mission; choisir une autre URL issue de Brave')
        if c.execute('SELECT COUNT(*) FROM fetched WHERE mission=?',(mid,)).fetchone()[0]>=cfg['page_limit']: raise ValueError('Plafond de lecture atteint')
        fid=c.execute("INSERT INTO fetched(mission,url,state) VALUES(?,?,'tentée')",(mid,target)).lastrowid
    try: data=fetch_page(target)
    except Exception as e:
        diagnostic=classify_failure(e)
        with s.db() as c: c.execute("UPDATE fetched SET state='échec',content=? WHERE id=?",(json.dumps({'failure':diagnostic},ensure_ascii=False),fid))
        raise ValueError('Lecture indisponible : '+diagnostic['code']+' '+diagnostic['message']+' · '+diagnostic['advice']) from None
    with s.db() as c: c.execute("UPDATE fetched SET state='reçue',content=? WHERE id=?",(json.dumps(data,ensure_ascii=False),fid))
    return {**data,'page_ref':fid}

