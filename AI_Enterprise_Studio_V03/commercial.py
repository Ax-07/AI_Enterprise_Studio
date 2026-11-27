"""Project-scoped commercial preparation. No publisher, payment or contact connector."""
import hashlib,json,re
from urllib.parse import urlsplit
import intelligence as intel
import portfolio
import research
from departments import commercial_economics, commercial_validation, commercial_evidence, commercial_qualification

LIMIT='Préparation interne uniquement. Citations vérifiées dans des extraits locaux, interprétation non certifiée. Aucun prospect contacté, aucune exposition mesurée, aucune vente ni dépense commerciale. Un protocole n’est pas un test exécuté.'
ACTIONS={'commercial_signal':'ORION','commercial_offer':'HERMES','commercial_economics':'MIDAS','commercial_review':'SENTINEL','commercial_extend':'SENTINEL'}
KINDS=('buyer_problem','competitor_offer','competitor_price','alternative','constraint')
OFFER_FIELDS=('audience','problem','offer','deliverables','price_cents','channel','metric','sample_size','success_min','duration_days','signal_ids','risks')
OFFER_TEXT=('audience','problem','offer','deliverables','channel','risks')
OFFER_LIMIT=800

def init(c):
    first_recovery=not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='commercial_followup_retries'").fetchone()
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
        CREATE TABLE IF NOT EXISTS commercial_followups(
        campaign INTEGER PRIMARY KEY REFERENCES campaigns(id),base_offer INTEGER NOT NULL UNIQUE REFERENCES commercial_offers(id),
        resulting_offer INTEGER UNIQUE REFERENCES commercial_offers(id),created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS commercial_signals_project ON commercial_signals(project,id);
        CREATE INDEX IF NOT EXISTS commercial_offers_project ON commercial_offers(project,id);""")

    # Create and populate atomically. Only the pre-upgrade history can qualify.
    c.execute('SAVEPOINT followup_upgrade')
    c.execute("""CREATE TABLE IF NOT EXISTS commercial_followup_retries(
        original_campaign INTEGER PRIMARY KEY REFERENCES commercial_followups(campaign),
        campaign INTEGER UNIQUE REFERENCES campaigns(id),resulting_offer INTEGER UNIQUE REFERENCES commercial_offers(id),
        reason TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP)""")
    if first_recovery:capture_legacy_no_search(c)
    c.execute('RELEASE followup_upgrade')

def capture_legacy_no_search(c):
    """Recognize only the observed V0.4.5 zero-attempt delegation defect."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_plan_queue'").fetchone():return
    for row in c.execute("""SELECT f.campaign,ca.permissions,ca.search_cap,cm.mission
        FROM commercial_followups f JOIN campaigns ca ON ca.id=f.campaign
        JOIN enterprise_plan_queue q ON q.campaign=ca.id
        JOIN campaign_missions cm ON cm.campaign=ca.id JOIN missions m ON m.id=cm.mission
        WHERE f.resulting_offer IS NULL AND ca.state='terminé' AND ca.search_cap>0
        AND cm.kind='commercial' AND m.mode='cloud' AND m.state='terminée' AND m.error=''
        AND (SELECT COUNT(*) FROM campaign_missions WHERE campaign=ca.id)=1"""):
        mid=row['mission']
        if not intel.decode(row['permissions']).get('research'):continue
        if any(c.execute('SELECT 1 FROM '+table+' WHERE mission=?',(mid,)).fetchone() for table in ('searches','fetched','commercial_signals','commercial_offers')):continue
        tasks=list(c.execute("SELECT agent,state,turns FROM tasks WHERE mission=? ORDER BY id",(mid,)))
        if [tuple(t) for t in tasks]!=[('ATLAS','terminée',2),('ORION','terminée',1)]:continue
        events=list(c.execute("SELECT agent,action,args,ok FROM events WHERE mission=? ORDER BY id",(mid,)))
        if [(e['agent'],e['action'],e['ok']) for e in events]!=[('ATLAS','delegate',1),('ORION','finish',1),('ATLAS','finish',1)]:continue
        args=intel.decode(events[0]['args'])
        if args.get('target')!='ORION' or not re.search(r'\bbrave (?:est|était) indisponible\b',args.get('text',''),re.I):continue
        c.execute('INSERT OR IGNORE INTO commercial_followup_retries(original_campaign,reason) VALUES(?,?)',
            (row['campaign'],'Historique V0.4.5 : délégation Brave indisponible malgré quota positif, aucune tentative réseau. Une nouvelle autorisation requise.'))

def followup(c,cid):
    return c.execute("""SELECT campaign,base_offer,resulting_offer,created,NULL AS recovery_of FROM commercial_followups WHERE campaign=?
        UNION ALL SELECT r.campaign,f.base_offer,r.resulting_offer,r.created,r.original_campaign AS recovery_of
        FROM commercial_followup_retries r JOIN commercial_followups f ON f.campaign=r.original_campaign WHERE r.campaign=?""",(cid,cid)).fetchone()

def followup_mission(c,mid):
    link=c.execute('SELECT campaign FROM campaign_missions WHERE mission=?',(mid,)).fetchone()
    return followup(c,link['campaign']) if link else None

def followup_outcome(c,mid,follow):
    attempts=c.execute('SELECT COUNT(*) FROM searches WHERE mission=?',(mid,)).fetchone()[0]
    state=c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0]
    return {'search_attempts':attempts,'state':'offre_enrichie' if follow['resulting_offer'] is not None else
        'en_cours' if state=='en cours' else 'recherche_sans_nouvelle_offre' if attempts else 'recherche_non_commencee',
        'legacy_retry_available':bool(c.execute('SELECT 1 FROM commercial_followup_retries WHERE original_campaign=? AND campaign IS NULL',(follow['campaign'],)).fetchone())}

def eligible_followup(c,pid,aid):
    if not aid:return None
    offer=project_status(c,pid)['offer']
    if not offer or offer['artifact']!=aid or offer['state']!='preparation_incomplete':return None
    if set(offer['gaps'])!={'indices_documentaires_insuffisants','revue_independante_manquante_ou_reserves'}:return None
    if not offer['review'] or offer['review']['verdict']!='study_further':return None
    if not offer['economics'] or offer['economics']['result']['monthly_result_cents']<=0:return None
    # No repeat except a migration-captured, proven zero-attempt legacy case.
    past=list(c.execute("""SELECT f.*,r.original_campaign,r.campaign AS retry_campaign FROM commercial_followups f
        JOIN commercial_offers o ON o.id=f.base_offer LEFT JOIN commercial_followup_retries r ON r.original_campaign=f.campaign
        WHERE o.project=? AND o.artifact=?""",(pid,aid)))
    if not past:return offer
    if len(past)==1 and past[0]['base_offer']==offer['id'] and past[0]['original_campaign'] is not None and past[0]['retry_campaign'] is None and past[0]['resulting_offer'] is None:
        return {**offer,'recovery_of':past[0]['campaign']}
    return None

def authorize_followup(c,cid,pid,aid,oid):
    offer=eligible_followup(c,pid,aid)
    if type(oid) is not int or not offer or offer['id']!=oid:raise ValueError('Offre à compléter non admissible ou modifiée')
    if offer.get('recovery_of') is not None:
        changed=c.execute('UPDATE commercial_followup_retries SET campaign=? WHERE original_campaign=? AND campaign IS NULL',(cid,offer['recovery_of'])).rowcount
        if changed!=1:raise ValueError('Récupération déjà autorisée')
    else:c.execute('INSERT INTO commercial_followups(campaign,base_offer) VALUES(?,?)',(cid,oid))

def scope(c,mid):
    return c.execute("""SELECT cp.project,ca.source,ca.state,ca.permissions,m.mode,m.state AS mission_state,p.state AS project_state
        FROM campaign_missions cm JOIN campaigns ca ON ca.id=cm.campaign
        JOIN campaign_projects cp ON cp.campaign=ca.id JOIN projects p ON p.id=cp.project
        JOIN missions m ON m.id=cm.mission WHERE cm.mission=? AND cm.kind='commercial' AND cp.scope='commercial'""",(mid,)).fetchone()

def _obj(text,fields):
    return commercial_validation.obj(text,fields,intel=intel)

def _text(d,k,lo=3,hi=1200):
    return commercial_validation.text(d,k,lo,hi)

def _int(d,k,lo,hi):
    return commercial_validation.bounded_field(d,k,lo,hi)

def _id(target):
    return commercial_validation.numeric_id(target)

def _proof(c,row):
    return commercial_evidence.proof(c,row,intel=intel)

def signals(c,pid,mid=None,limit=12):
    return commercial_evidence.signals(c,pid,mid,limit,intel=intel,research=research,proof=_proof)

def _signal(c,pid,sid,mid):
    return commercial_evidence.signal(c,pid,sid,mid,proof=_proof)

def _offer(c,pid,mid,oid):
    row=c.execute('SELECT * FROM commercial_offers WHERE id=? AND project=? AND mission=?',(oid,pid,mid)).fetchone()
    if not row:raise ValueError('Offre de la mission requise')
    return row

def economics_result(plan,d):
    return commercial_economics.economics_result(plan,d)

def execute(c,t,action,target,text,detail):
    mid=t['mission'];agent=t['agent'];sc=scope(c,mid)
    if (not sc or sc['state']!='actif' or sc['mission_state']!='en cours' or sc['mode']!='cloud'
        or sc['project_state']!='active' or ACTIONS.get(action)!=agent or detail):
        raise ValueError('Action commerciale interne hors périmètre')
    flags=intel.decode(sc['permissions'])
    if not flags['market'] or (action=='commercial_signal' and not flags['research']) or (action=='commercial_review' and not flags['tests']):
        raise ValueError('Autorisation manquante')
    pid=sc['project'];follow=followup_mission(c,mid)
    if follow and action not in ('commercial_signal','commercial_extend'):raise ValueError('Complément documentaire : offre et économie historiques immuables')
    if action=='commercial_extend':
        if not follow or not flags['tests'] or follow['resulting_offer'] is not None or _id(target)!=follow['base_offer']:raise ValueError('Complément non autorisé')
        d=_obj(text,('signal_ids','verdict','gaps','risks'))
        _text(d,'gaps',10,1600);_text(d,'risks',5,800)
        if d['verdict'] not in ('revise','study_further','propose_future_test'):raise ValueError('Verdict non autorisé')
        if not c.execute("SELECT 1 FROM tasks WHERE mission=? AND agent='ORION' AND state='terminée'",(mid,)).fetchone():raise ValueError('Recherche ORION terminée requise')
        base=c.execute('SELECT * FROM commercial_offers WHERE id=? AND project=?',(follow['base_offer'],pid)).fetchone()
        if not base or base['artifact']!=sc['source']:raise ValueError('Référence d’origine modifiée')
        art=portfolio.latest(c,pid)
        if not art or art['id']!=base['artifact'] or hashlib.sha256(art['content'].encode()).hexdigest()!=base['artifact_sha256']:raise ValueError('Empreinte d’origine modifiée')
        old=offer_status(c,base)
        if set(old['gaps'])!={'indices_documentaires_insuffisants','revue_independante_manquante_ou_reserves'}:raise ValueError('Offre d’origine non admissible')
        ids=d['signal_ids']
        if not isinstance(ids,list) or not 1<=len(ids)<=10 or any(type(x) is not int or x<=0 or x>9007199254740991 for x in ids) or len(set(ids))!=len(ids):raise ValueError('IDs de signaux invalides')
        new=False
        for sid in ids:
            signal,proof=_signal(c,pid,sid,mid)
            if signal['mission']==mid:
                raw=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(signal['page'],)).fetchone()[0])
                if research.excerpt_quality(raw['texte'])=='text_available' and not c.execute("""SELECT 1 FROM commercial_signals s JOIN fetched f ON f.id=s.page
                    WHERE s.project=? AND s.mission<>? AND s.kind=? AND s.quote=? AND f.url=?""",(pid,mid,signal['kind'],signal['quote'],proof['url'])).fetchone():new=True
        if not new:raise ValueError('Au moins un nouvel indice documentaire exploitable requis')
        plan=intel.decode(base['plan'])
        if not set(plan['signal_ids']).issubset(ids):raise ValueError('Conserver les signaux historiques de l’offre')
        eco=old['economics'];plan['signal_ids']=ids;plan['risks']=d['risks']
        oid=c.execute('INSERT INTO commercial_offers(project,mission,artifact,artifact_sha256,plan) VALUES(?,?,?,?,?)',
            (pid,mid,base['artifact'],base['artifact_sha256'],intel.canonical(plan))).lastrowid
        eid=c.execute('INSERT INTO commercial_economics(offer,mission,assumptions,result) VALUES(?,?,?,?)',
            (oid,mid,intel.canonical(eco['assumptions']),intel.canonical(eco['result']))).lastrowid
        rid=c.execute('INSERT INTO commercial_reviews(offer,mission,review) VALUES(?,?,?)',
            (oid,mid,intel.canonical({'verdict':d['verdict'],'gaps':d['gaps']}))).lastrowid
        table='commercial_followup_retries' if follow['recovery_of'] is not None else 'commercial_followups'
        c.execute('UPDATE '+table+' SET resulting_offer=? WHERE campaign=?',(oid,follow['campaign']))
        return {'offer':oid,'base_offer':base['id'],'economics':eid,'economics_reused_from':eco['id'],'review':rid,'verdict':d['verdict'],'external_authorized':False,'limit':LIMIT}
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
    return commercial_qualification.offer_status(c,row,intel=intel,signal=_signal,research=research,portfolio=portfolio,hashlib=hashlib,urlsplit=urlsplit,commercial_economics=commercial_economics,economics_result=economics_result,limit=LIMIT)

def project_status(c,pid,mid=None):
    row=c.execute("""SELECT o.* FROM commercial_offers o JOIN missions m ON m.id=o.mission WHERE o.project=?
        AND (m.state='terminée' OR o.mission=?) AND (? IS NULL OR o.mission<=?) ORDER BY o.id DESC LIMIT 1""",(pid,mid,mid,mid)).fetchone()
    return {'project':pid,'signals':signals(c,pid,mid),'offer':offer_status(c,row) if row else None,'limit':LIMIT}

def context(c,mid):
    sc=scope(c,mid)
    if not sc:return None
    pid=sc['project'];p=portfolio.project(c,pid)
    opp=c.execute('SELECT id,title,body,next_test FROM opportunities WHERE id=?',(p['opportunity'],)).fetchone()
    art=portfolio.latest(c,pid)
    v=project_status(c,pid,mid)
    follow=followup_mission(c,mid)
    if follow:v['followup']={**dict(follow),'outcome':followup_outcome(c,mid,follow),'limit':'Prix, offre, protocole et hypothèses économiques conservés; risques et revue actualisés uniquement si nouvel indice. Aucun lancement.'}
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
