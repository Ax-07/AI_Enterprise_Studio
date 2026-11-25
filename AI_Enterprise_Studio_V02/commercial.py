"""Project-scoped commercial preparation. No publisher, payment or contact connector."""
import hashlib,json
from urllib.parse import urlsplit
import intelligence as intel
import portfolio
import research

LIMIT='Préparation interne uniquement. Citations vérifiées dans des extraits locaux, interprétation non certifiée. Aucun prospect contacté, aucune exposition mesurée, aucune vente ni dépense commerciale. Un protocole n’est pas un test exécuté.'
ACTIONS={'commercial_signal':'ORION','commercial_offer':'HERMES','commercial_economics':'MIDAS','commercial_review':'SENTINEL'}
KINDS=('buyer_problem','competitor_offer','competitor_price','alternative','constraint')
OFFER_FIELDS=('audience','problem','offer','deliverables','price_cents','channel','metric','sample_size','success_min','duration_days','signal_ids','risks')
OFFER_TEXT=('audience','problem','offer','deliverables','channel','risks')
OFFER_LIMIT=800

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS commercial_signals(
        id INTEGER PRIMARY KEY, project INTEGER NOT NULL REFERENCES projects(id),
        mission INTEGER NOT NULL REFERENCES missions(id), page INTEGER NOT NULL REFERENCES fetched(id),
        kind TEXT NOT NULL, quote TEXT NOT NULL, interpretation TEXT NOT NULL, proof TEXT NOT NULL,
        created TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(project,page,kind,quote));
        CREATE TABLE IF NOT EXISTS commercial_offers(
        id INTEGER PRIMARY KEY, project INTEGER NOT NULL REFERENCES projects(id),
        mission INTEGER NOT NULL UNIQUE REFERENCES missions(id), artifact INTEGER REFERENCES artifacts(id),
        artifact_sha256 TEXT, plan TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS commercial_economics(
        id INTEGER PRIMARY KEY, offer INTEGER NOT NULL UNIQUE REFERENCES commercial_offers(id),
        mission INTEGER NOT NULL REFERENCES missions(id), assumptions TEXT NOT NULL, result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commercial_reviews(
        id INTEGER PRIMARY KEY, offer INTEGER NOT NULL UNIQUE REFERENCES commercial_offers(id),
        mission INTEGER NOT NULL REFERENCES missions(id), review TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commercial_recoveries(task INTEGER PRIMARY KEY REFERENCES tasks(id),mission INTEGER NOT NULL REFERENCES missions(id),created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS commercial_signals_project ON commercial_signals(project,id);
        CREATE INDEX IF NOT EXISTS commercial_offers_project ON commercial_offers(project,id);""")

def scope(c,mid):
    return c.execute("""SELECT cp.project,ca.source,ca.state,ca.permissions,m.mode,m.state AS mission_state,p.state AS project_state
        FROM campaign_missions cm JOIN campaigns ca ON ca.id=cm.campaign
        JOIN campaign_projects cp ON cp.campaign=ca.id JOIN projects p ON p.id=cp.project
        JOIN missions m ON m.id=cm.mission WHERE cm.mission=? AND cm.kind='commercial' AND cp.scope='commercial'""",(mid,)).fetchone()

def _obj(text,fields):
    if not isinstance(text,str) or len(text)>10000:raise ValueError('JSON commercial trop long')
    d=intel.decode(text)
    if not isinstance(d,dict) or set(d)!=set(fields):raise ValueError('Champs requis : '+', '.join(fields))
    return d

def _text(d,k,lo=3,hi=1200):
    if not isinstance(d[k],str):raise ValueError(f'Texte invalide : {k}; chaîne JSON de {lo} à {hi} caractères requise, type reçu {type(d[k]).__name__}')
    n=len(d[k].strip())
    if not lo<=n<=hi:raise ValueError(f'Texte invalide : {k}; {n} caractères reçus, {lo} à {hi} requis; raccourcir sans perdre les risques essentiels')

def _int(d,k,lo,hi):
    if type(d[k]) is not int or not lo<=d[k]<=hi:raise ValueError(f'Valeur invalide : {k}; entier JSON de {lo} à {hi} requis')

def _id(target):
    if not target.isascii() or not target.isdigit() or len(target)>12 or int(target)<=0:raise ValueError('ID numérique requis')
    return int(target)

def _proof(c,row):
    p=intel.page_reference(c,row['mission'],row['page'])
    content=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(row['page'],)).fetchone()[0])
    if row['quote'] not in content['texte'] or p!=intel.decode(row['proof']):raise ValueError('Citation ou empreinte modifiée')
    return p

def signals(c,pid,mid=None,limit=12):
    out=[]
    for row in c.execute("""SELECT s.* FROM commercial_signals s JOIN missions m ON m.id=s.mission
        WHERE s.project=? AND m.mode='cloud' AND (m.state='terminée' OR s.mission=?)
        ORDER BY s.id DESC LIMIT ?""",(pid,mid,limit)):
        try: proof=_proof(c,row)
        except (ValueError,TypeError,KeyError,AttributeError):continue
        excerpt=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(row['page'],)).fetchone()[0])['texte']
        out.append({**{k:row[k] for k in ('id','mission','kind','quote','interpretation','created')},'proof':proof,'quality':research.excerpt_quality(excerpt)})
    return out

def _signal(c,pid,sid,mid):
    row=c.execute("""SELECT s.* FROM commercial_signals s JOIN missions m ON m.id=s.mission
        WHERE s.id=? AND s.project=? AND m.mode='cloud' AND (m.state='terminée' OR s.mission=?)""",(sid,pid,mid)).fetchone()
    if not row:raise ValueError('Signal de cette activité requis')
    return row,_proof(c,row)

def _offer(c,pid,mid,oid):
    row=c.execute('SELECT * FROM commercial_offers WHERE id=? AND project=? AND mission=?',(oid,pid,mid)).fetchone()
    if not row:raise ValueError('Offre de la mission requise')
    return row

def economics_result(plan,d):
    contribution=plan['price_cents']-d['variable_cost_cents']
    adverse=plan['price_cents']-(d['variable_cost_cents']*120+99)//100
    return {'contribution_cents':contribution,'monthly_result_cents':contribution*d['monthly_units']-d['fixed_month_cents'],
        'breakeven_units':(d['fixed_month_cents']+contribution-1)//contribution if contribution>0 else None,
        'adverse_monthly_result_cents':adverse*max(1,d['monthly_units']//2)-d['fixed_month_cents'],
        'classification':'hypothèses EUR, avant impôt et coûts initiaux non inclus'}

def execute(c,t,action,target,text,detail):
    mid=t['mission'];agent=t['agent'];sc=scope(c,mid)
    if (not sc or sc['state']!='actif' or sc['mission_state']!='en cours' or sc['mode']!='cloud'
        or sc['project_state']!='active' or ACTIONS.get(action)!=agent or detail):
        raise ValueError('Action commerciale interne hors périmètre')
    flags=intel.decode(sc['permissions'])
    if not flags['market'] or (action=='commercial_signal' and not flags['research']) or (action=='commercial_review' and not flags['tests']):
        raise ValueError('Autorisation manquante')
    pid=sc['project']
    if action=='commercial_signal':
        d=_obj(text,('kind','quote','interpretation'));page=_id(target)
        if d['kind'] not in KINDS:raise ValueError('Catégorie de signal invalide')
        _text(d,'quote',12,500);_text(d,'interpretation',10,600)
        proof=intel.page_reference(c,mid,page)
        raw=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(page,)).fetchone()[0])
        if d['quote'] not in raw['texte']:raise ValueError('Citation exacte absente de la page effectivement lue')
        if c.execute('SELECT COUNT(*) FROM commercial_signals WHERE mission=?',(mid,)).fetchone()[0]>=10:raise ValueError('Plafond de 10 signaux')
        if c.execute('SELECT 1 FROM commercial_signals WHERE project=? AND page=? AND kind=? AND quote=?',(pid,page,d['kind'],d['quote'])).fetchone():raise ValueError('Signal déjà enregistré')
        sid=c.execute('INSERT INTO commercial_signals(project,mission,page,kind,quote,interpretation,proof) VALUES(?,?,?,?,?,?,?)',
            (pid,mid,page,d['kind'],d['quote'],d['interpretation'],intel.canonical(proof))).lastrowid
        return {'signal':sid,'proof':proof,'classification':'indice documentaire, pas preuve de demande'}
    if action=='commercial_offer':
        if target:raise ValueError('Cible vide pour une offre')
        d=_obj(text,OFFER_FIELDS)
        for k in OFFER_TEXT:_text(d,k,5,OFFER_LIMIT)
        _int(d,'price_cents',1,10000000);_int(d,'sample_size',1,10000);_int(d,'success_min',1,d['sample_size']);_int(d,'duration_days',1,90)
        if d['metric'] not in ('qualified_interest','consented_demo_request','paid_order_future'):raise ValueError('Métrique future invalide')
        ids=d['signal_ids']
        if not isinstance(ids,list) or len(ids)>10 or any(type(x) is not int or x<=0 or x>9007199254740991 for x in ids) or len(set(ids))!=len(ids):raise ValueError('Références de signaux invalides')
        for sid in ids:_signal(c,pid,sid,mid)
        if c.execute('SELECT 1 FROM commercial_offers WHERE mission=?',(mid,)).fetchone():raise ValueError('Une seule offre par mission')
        aid=sc['source'];sha=None
        if aid is not None:
            art=c.execute("""SELECT a.content FROM artifacts a JOIN project_missions pm ON pm.mission=a.mission
                WHERE a.id=? AND pm.project=? AND a.agent='NEXUS'""",(aid,pid)).fetchone()
            if not art:raise ValueError('Référence produit hors activité')
            sha=hashlib.sha256(art['content'].encode()).hexdigest()
        oid=c.execute('INSERT INTO commercial_offers(project,mission,artifact,artifact_sha256,plan) VALUES(?,?,?,?,?)',
            (pid,mid,aid,sha,intel.canonical(d))).lastrowid
        return {'offer':oid,'state':'brouillon_interne','commercial_spend_cents':0,'observations':0,'sales':0,'limit':LIMIT}
    oid=_id(target);row=_offer(c,pid,mid,oid);plan=intel.decode(row['plan'])
    if action=='commercial_economics':
        d=_obj(text,('variable_cost_cents','fixed_month_cents','monthly_units','rationale'))
        _int(d,'variable_cost_cents',0,10000000);_int(d,'fixed_month_cents',0,100000000);_int(d,'monthly_units',1,100000);_text(d,'rationale',20,1200)
        if c.execute('SELECT 1 FROM commercial_economics WHERE offer=?',(oid,)).fetchone():raise ValueError('Évaluation déjà enregistrée')
        result=economics_result(plan,d)
        rid=c.execute('INSERT INTO commercial_economics(offer,mission,assumptions,result) VALUES(?,?,?,?)',
            (oid,mid,intel.canonical(d),intel.canonical(result))).lastrowid
        return {'economics':rid,**result}
    if action=='commercial_review':
        d=_obj(text,('verdict','gaps'))
        if d['verdict'] not in ('revise','study_further','propose_future_test'):raise ValueError('Verdict non autorisé')
        _text(d,'gaps',10,1600)
        if not c.execute('SELECT 1 FROM commercial_economics WHERE offer=?',(oid,)).fetchone():raise ValueError('Évaluation MIDAS requise avant revue')
        if c.execute('SELECT 1 FROM commercial_reviews WHERE offer=?',(oid,)).fetchone():raise ValueError('Revue déjà enregistrée')
        rid=c.execute('INSERT INTO commercial_reviews(offer,mission,review) VALUES(?,?,?)',(oid,mid,intel.canonical(d))).lastrowid
        return {'review':rid,'verdict':d['verdict'],'limit':'Avis indépendant, pas autorisation externe'}
    raise ValueError('Action inconnue')

def offer_status(c,row):
    plan=intel.decode(row['plan']);pid=row['project'];mid=row['mission']
    evidence=[];invalid=[]
    for sid in plan['signal_ids']:
        try:
            s,p=_signal(c,pid,sid,mid)
            excerpt=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(s['page'],)).fetchone()[0])['texte']
            evidence.append({'id':sid,'kind':s['kind'],'proof':p,'quote':s['quote'],'interpretation':s['interpretation'],'quality':research.excerpt_quality(excerpt)})
        except (ValueError,TypeError,KeyError,AttributeError):invalid.append(sid)
    eco=c.execute('SELECT * FROM commercial_economics WHERE offer=?',(row['id'],)).fetchone()
    review=c.execute('SELECT * FROM commercial_reviews WHERE offer=?',(row['id'],)).fetchone()
    art=portfolio.latest(c,pid);proofs=[];lab=None
    exact=bool(art and art['id']==row['artifact'] and hashlib.sha256(art['content'].encode()).hexdigest()==row['artifact_sha256'])
    if exact:
        proofs=portfolio.evidence(c,art);lab=portfolio.laboratory.canonical(c,art)
    independent=any(p['agent']=='SENTINEL' and p['status']=='passed' for p in proofs) and not any(p['agent']=='SENTINEL' and p['status']=='failed' for p in proofs)
    if exact and portfolio.laboratory.supports(art):independent=independent and bool(lab and lab['status']=='passed')
    usable=[x for x in evidence if x['quality']=='text_available']
    domains={urlsplit(x['proof']['url']).hostname for x in usable}
    kinds={x['kind'] for x in usable}
    economics={'id':eco['id'],'assumptions':intel.decode(eco['assumptions']),'result':intel.decode(eco['result'])} if eco else None
    audit={'id':review['id'],**intel.decode(review['review'])} if review else None
    gaps=[]
    if not independent:gaps.append('preuve_technique_independante_manquante')
    if invalid:gaps.append('signaux_invalides')
    if len(domains)<2 or 'buyer_problem' not in kinds or not kinds.intersection({'competitor_offer','competitor_price','alternative'}):gaps.append('indices_documentaires_insuffisants')
    if not economics or economics['result']!=economics_result(plan,economics['assumptions']) or economics['result']['monthly_result_cents']<=0 or economics['result']['contribution_cents']<=0:gaps.append('scenario_economique_manquant_ou_defavorable')
    if not audit or audit['verdict']!='propose_future_test':gaps.append('revue_independante_manquante_ou_reserves')
    m=c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()
    if m['state']!='terminée':gaps.append('mission_non_terminee')
    return {'id':row['id'],'project':pid,'mission':mid,'artifact':row['artifact'],'artifact_sha256':row['artifact_sha256'],
        'plan':plan,'evidence':evidence,'invalid_signal_ids':invalid,'economics':economics,'review':audit,
        'technical_proofs':proofs,'laboratory':lab,'gaps':gaps,
        'state':'proposition_a_examiner' if not gaps else 'preparation_incomplete',
        'observations':0,'sales':0,'commercial_spend_cents':0,'external_authorized':False,'limit':LIMIT}

def project_status(c,pid,mid=None):
    row=c.execute("""SELECT o.* FROM commercial_offers o JOIN missions m ON m.id=o.mission WHERE o.project=?
        AND (m.state='terminée' OR o.mission=?) ORDER BY o.id DESC LIMIT 1""",(pid,mid)).fetchone()
    return {'project':pid,'signals':signals(c,pid,mid),'offer':offer_status(c,row) if row else None,'limit':LIMIT}

def context(c,mid):
    sc=scope(c,mid)
    if not sc:return None
    pid=sc['project'];p=portfolio.project(c,pid)
    opp=c.execute('SELECT id,title,body,next_test FROM opportunities WHERE id=?',(p['opportunity'],)).fetchone()
    art=portfolio.latest(c,pid)
    v=project_status(c,pid,mid)
    v['activity']={'id':pid,'title':p['title'],'opportunity':dict(opp) if opp else None}
    v['reference']={'id':art['id'],'name':art['name'],'version':art['version'],
        'proofs':portfolio.evidence(c,art),'laboratory':portfolio.laboratory.canonical(c,art)} if art else None
    v['past_assessments']=[x for x in intel.ranking(c) if x['project']==pid][:3]
    return v

def offer_errors(c,t):
    rows=list(c.execute("SELECT action,ok,result FROM events WHERE mission=? AND task=? ORDER BY id DESC LIMIT 3",(t['mission'],t['id'])))
    out=[]
    for row in rows:
        if row['ok'] or row['action']!='commercial_offer':break
        try:err=json.loads(row['result']).get('erreur','')
        except (ValueError,TypeError,AttributeError):break
        if not isinstance(err,str) or not err.startswith(('Texte invalide : ','Valeur invalide : ','Champs requis : ','JSON commercial trop long','Métrique future invalide','Références de signaux invalides')):break
        out.append(err)
    return out

def recovery_task(c,mid,cfg):
    """One explicit repair of a failed offer, including legacy rollback of last event."""
    sc=scope(c,mid)
    if not sc or sc['state']!='bloqué' or sc['mission_state']!='bloquée' or sc['mode']!='cloud' or sc['project_state']!='active':return None
    if not intel.decode(sc['permissions'])['market']:return None
    m=c.execute("SELECT * FROM missions WHERE id=? AND engine='dynamic'",(mid,)).fetchone()
    if not m:return None
    t=c.execute("""SELECT * FROM tasks t WHERE mission=? AND state='prête' AND NOT EXISTS
        (SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    if not t or t['agent']!='HERMES' or t['turns']+1>=cfg['turn_limit']:return None
    if m['error']!='Trois outils refusés/échoués de suite sur tâche #'+str(t['id']):return None
    if c.execute('SELECT 1 FROM commercial_offers WHERE mission=?',(mid,)).fetchone() or c.execute('SELECT 1 FROM commercial_recoveries WHERE task=?',(t['id'],)).fetchone():return None
    errors=offer_errors(c,t)
    if len(errors)<2 or t['turns']<3:return None
    if c.execute("SELECT 1 FROM tasks WHERE mission=? AND agent='ORION' AND state='terminée'",(mid,)).fetchone() is None:return None
    if c.execute('SELECT COUNT(*) FROM events WHERE mission=?',(mid,)).fetchone()[0]>=cfg['call_limit']:return None
    calls,spent=c.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger WHERE mission=?',(mid,)).fetchone()
    if calls>=cfg['call_limit'] or spent>=cfg['mission_budget']:return None
    return t['id']

def correction(c,t):
    if t['agent']!='HERMES' or not scope(c,t['mission']):return []
    if c.execute('SELECT 1 FROM commercial_offers WHERE mission=?',(t['mission'],)).fetchone():return []
    errors=offer_errors(c,t)
    return errors if len(errors)>=2 else []

def status(c):
    return {'projects':[project_status(c,r['id']) for r in c.execute('SELECT id FROM projects ORDER BY id')],'limit':LIMIT}

def campaign(c,cid):
    return [context(c,r['mission']) for r in c.execute("SELECT mission FROM campaign_missions WHERE campaign=? AND kind='commercial' ORDER BY mission",(cid,))]
