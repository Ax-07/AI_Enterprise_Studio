"""Internal action handlers using the transaction supplied by moteur.execute.

No transaction ownership, permission grants, transport or imports of business
modules. Callers must enforce all shared authorization and mission guards.
Legacy dependencies are supplied at the point of use.
"""
import json
import re


def execute_commercial(c,t,a,target,text,detail,mode,commercial_execute):
    if mode!='cloud':raise ValueError('Préparation commerciale Cloud uniquement')
    return commercial_execute(c,t,a,target,text,detail)


def execute_assess_opportunity(c,mid,agent,target,text,detail,mode,assess):
    if mode!='cloud' or detail:raise ValueError('Évaluation Cloud, detail vide requis')
    return assess(c,mid,agent,target,text)


def execute_opportunity(c,mid,target,text,detail):
    if not target or len(target)>160 or not text.strip(): raise ValueError('Opportunité invalide')
    c.execute('INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,?,?) ON CONFLICT(mission,title) DO UPDATE SET body=excluded.body,next_test=excluded.next_test',(mid,target,text[:8000],detail[:2000]));return {'titre':target,'statut':'hypothèse','opportunity':c.execute('SELECT id FROM opportunities WHERE mission=? AND title=?',(mid,target)).fetchone()[0]}


def execute_calculate(text,calc):
    return {'expression':text,'resultat':calc(text),'note':'Exactitude arithmétique seulement; hypothèses non validées.'}


def execute_write_file(c,mid,agent,target,text,detail,latest,check):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.(md|txt|csv|json|py|html|css|js)',target,re.I) or '..' in target or not text.strip(): raise ValueError('Nom ou contenu invalide')
    if c.execute('SELECT COUNT(*) FROM artifacts WHERE mission=?',(mid,)).fetchone()[0]>=25: raise ValueError('Plafond de versions atteint')
    old=latest(c,mid,target)
    if old and old['content']==text: return {'nom':target,'version':old['version'],'identique':True}
    ver=old['version']+1 if old else 1
    aid=c.execute('INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,?,?,?,?,?)',(mid,target,ver,agent,text,detail[:1000])).lastrowid
    return {'fichier':aid,'nom':target,'version':ver,'controle':check(target,text),'note':'Brouillon interne enregistré en SQLite, aucun code exécuté.'}


def execute_list_files(c,mid,attached_artifact,reference_metadata):
    files=[dict(x) for x in c.execute('SELECT id,name,version,agent,description FROM artifacts WHERE mission=? ORDER BY id DESC',(mid,))]
    source=attached_artifact(c,mid)
    if source: files.append(reference_metadata(source))
    return files


def execute_read_or_check_file(c,mid,a,target,resolve_artifact,check):
    row,reference=resolve_artifact(c,mid,target)
    if not row: raise ValueError('Fichier absent')
    meta={'fichier':row['id'],'nom':row['name'],'version':row['version'],'mission_source':row['mission'],'reference':reference}
    if a=='read_file': return {**meta,'contenu':row['content']}
    return {**meta,**check(row['name'],row['content'])}


def execute_read_report(c,target):
    if not target.isdigit() or len(target)>12: raise ValueError('ID rapport invalide')
    r=c.execute('SELECT r.*,m.mode FROM reports r JOIN missions m ON m.id=r.mission WHERE r.id=?',(int(target),)).fetchone()
    if not r: raise ValueError('Rapport absent')
    return {'rapport_id':r['id'],'mission':r['mission'],'agent':r['agent'],'mode':r['mode'],'rapport_non_certifié':json.loads(r['report']),'sources_non_certifiées':json.loads(r['sources'])}


def execute_memory(c,target,text,detail):
    if target:
        match=re.fullmatch(r'opportunity:([1-9][0-9]{0,11})',target)
        if not match or text or detail:raise ValueError('Mémoire exacte : target=opportunity:ID, text et detail vides')
        o=c.execute('SELECT o.*,m.mode FROM opportunities o JOIN missions m ON m.id=o.mission WHERE o.id=?',(int(match[1]),)).fetchone()
        if not o:raise ValueError('Opportunité exacte absente')
        return {'résultats':[{'type':'opportunities','id':o['id'],'mission':o['mission'],'mode':o['mode'],'titre':o['title'],'extrait':o['body'][:1600],'next_test':o['next_test'][:1200],'partiel':len(o['body'])>1600 or len(o['next_test'])>1200}],'note':'Hypothèse historique exacte, non certifiée.'}
    terms=[w for w in re.findall(r'\w+',text.lower()) if len(w)>2][:5]
    if not terms: raise ValueError('Termes de recherche nécessaires')
    items=[]
    for table,col in [('opportunities','body'),('reports','report'),('requests','body'),('tasks','result')]:
        candidates=c.execute(f"SELECT id,mission,{col} AS data FROM {table} WHERE "+' OR '.join(f'LOWER({col}) LIKE ?' for _ in terms)+' ORDER BY id DESC LIMIT 4',tuple('%'+w+'%' for w in terms))
        for r in candidates: items.append({'type':table,'id':r['id'],'mission':r['mission'],'extrait':r['data'][:1200],'partiel':len(r['data'])>1200,'mode':c.execute('SELECT mode FROM missions WHERE id=?',(r['mission'],)).fetchone()[0]})
    return {'résultats':items,'note':'Recherche lexicale; rapports et simulations non certifiés.'}
