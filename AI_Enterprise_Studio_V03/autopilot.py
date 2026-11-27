"""Bounded, persistent internal campaign scheduler. No provider outside the mission engine."""
import json, hashlib
from departments import accounting
import protocol_recovery
import working_memory
import portfolio
import commercial
import incidents
import laboratory
import improvement
import connectors
from decimal import Decimal, InvalidOperation

ACTIVE='actif'
FLAGS=('research','production','tests','market')
ROLES={'opportunity':{'ORION','MIDAS','SENTINEL'},'create':{'NEXUS'},'improve':{'NEXUS'},
       'functional':{'SENTINEL'},'market':{'HERMES','MIDAS'},'commercial':{'ORION','HERMES','MIDAS','SENTINEL'}}

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS campaigns(
        id INTEGER PRIMARY KEY, goal TEXT NOT NULL, budget INTEGER NOT NULL,
        max_missions INTEGER NOT NULL, permissions TEXT NOT NULL, search_cap INTEGER NOT NULL,
        source INTEGER, state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
        created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS campaign_missions(
        campaign INTEGER NOT NULL REFERENCES campaigns(id), mission INTEGER PRIMARY KEY REFERENCES missions(id),
        kind TEXT NOT NULL, artifact INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS campaign_links ON campaign_missions(campaign);
        CREATE UNIQUE INDEX IF NOT EXISTS campaign_one_active ON campaigns(state) WHERE state='actif';""")
    c.execute("UPDATE campaigns SET state='interrompu',reason='Redémarrage : reprise explicite requise; réservations conservées.' WHERE state='actif'")

def active(c):
    return c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone() is not None

def link(c,mid):
    return c.execute("""SELECT c.*,cm.kind,cm.artifact FROM campaigns c JOIN campaign_missions cm ON cm.campaign=c.id WHERE cm.mission=?""",(mid,)).fetchone()

def costs(c,cid):
    return accounting.campaign_total(c,cid)

def searches(c,cid):
    return c.execute("""SELECT COUNT(*) FROM searches s JOIN campaign_missions cm ON cm.mission=s.mission WHERE cm.campaign=?""",(cid,)).fetchone()[0]

def reserve(c,mid,amount):
    p=link(c,mid)
    if p:
        import periodic
        periodic.guard_campaign(c,p['id'])
        if p['state']!=ACTIVE: raise RuntimeError('Autopilote non actif')
        if costs(c,p['id'])+amount>p['budget']: raise RuntimeError('Enveloppe Autopilote insuffisante pour réserver cet appel.')

def search_allowed(c,mid):
    import periodic
    periodic.guard_mission(c,mid)
    p=link(c,mid)
    if p and (p['state']!=ACTIVE or not json.loads(p['permissions'])['research'] or searches(c,p['id'])>=p['search_cap']):
        raise ValueError('Quota de recherches Autopilote atteint ou non autorisé')

def permitted(c,mid,agent,base):
    p=link(c,mid)
    if not p:return set(base)-set(commercial.ACTIONS),None
    flags=json.loads(p['permissions']);kind=p['kind']
    allowed=set(base)
    scope=portfolio.scope(c,p['id'])
    if scope and scope['scope']=='draft_recovery':
        allowed&=({'delegate','finish'} if agent=='ATLAS' else {'read_file','test_file','check_file','list_files','finish'} if agent=='SENTINEL' else set())
    if kind!='commercial':allowed-=set(commercial.ACTIONS)
    else:
        if not flags['market']:allowed-=set(commercial.ACTIONS)
        if not flags['research']:allowed.discard('commercial_signal')
        if not flags['tests']:allowed-={'commercial_review','commercial_extend'}
        follow=commercial.followup(c,p['id'])
        if follow:
            allowed&={'finish','delegate','search','read','commercial_signal','commercial_extend'}
            if agent!='ORION':allowed-={'search','read','commercial_signal'}
        else:allowed.discard('commercial_extend')
    if not flags['research'] or p['search_cap']==0: allowed-={'search','read'}
    elif searches(c,p['id'])>=p['search_cap']:allowed.discard('search')
    if not flags['production'] or kind not in ('create','improve'): allowed.discard('write_file')
    if not flags['tests'] or kind!='functional': allowed.discard('test_file')
    if not flags['tests']: allowed.discard('check_file')
    if kind!='opportunity': allowed-={'opportunity','assess_opportunity'}
    if not flags['research'] or kind not in ('opportunity','market') or not connectors.campaign_status(c,p['id'])['max_calls']:allowed.discard('connector')
    return allowed,p

def delegable(p,c=None):
    agents=set(ROLES[p['kind']])
    if c is not None and commercial.followup(c,p['id']):agents&={'ORION','SENTINEL'}
    if p['kind'] in ('opportunity','commercial') and not json.loads(p['permissions'])['tests']:agents.discard('SENTINEL')
    return agents

def guard(c,mid,agent,action,target,base):
    allowed,p=permitted(c,mid,agent,base)
    if not p:return
    if p['state']!=ACTIVE: raise ValueError('Autopilote arrêté')
    if action not in allowed: raise ValueError('Action hors autorisations Autopilote')
    scope=portfolio.scope(c,p['id'])
    if scope and scope['scope']=='draft_recovery' and action in ('read_file','test_file','check_file') and target!='ref:'+str(p['artifact']):
        raise ValueError('Audit de récupération : référence exacte uniquement')
    if action=='delegate' and commercial.followup(c,p['id']) and target not in ('ORION','SENTINEL'):raise ValueError('Complément documentaire : ORION et SENTINEL uniquement')
    if action=='delegate' and target not in delegable(p,c): raise ValueError('Agent hors périmètre de cette mission Autopilote')

def _campaign(c,cid):
    return c.execute('SELECT * FROM campaigns WHERE id=?',(cid,)).fetchone()

def _missions(c,cid):
    return list(c.execute("""SELECT cm.kind,cm.artifact,m.id,m.state,m.error,m.title
        FROM campaign_missions cm JOIN missions m ON m.id=cm.mission WHERE cm.campaign=? ORDER BY m.id""",(cid,)))

def recovery_kind(c,mid,cfg):
    if protocol_recovery.recovery_task(c,mid,cfg):return 'protocol'
    if working_memory.recovery_task(c,mid,cfg):return 'memory'
    if commercial.recovery_task(c,mid,cfg):return 'commercial'
    if incidents.eligible(c,mid,cfg):return 'transient'
    return None

def readiness(c,cfg,locked=False):
    campaign=c.execute("SELECT id FROM campaigns WHERE state='actif'").fetchone()
    mission=c.execute("SELECT id FROM missions WHERE state='en cours' ORDER BY id LIMIT 1").fetchone()
    pending=c.execute("SELECT COUNT(*) FROM requests WHERE state='en attente'").fetchone()[0]
    remaining=max(0,cfg['budget']-accounting.global_total(c))
    blockers=[]
    if campaign:blockers.append('Campagne #'+str(campaign[0])+' en cours')
    if mission:blockers.append('Mission #'+str(mission[0])+' en cours')
    if locked and not campaign and not mission:blockers.append('Moteur local occupé (comparaison, test ou finalisation)')
    if pending:blockers.append(str(pending)+' décision(s) en attente')
    if not cfg['key']:blockers.append('Clé OpenAI non configurée')
    if remaining<10000:blockers.append('Budget global restant inférieur à 0,01 USD')
    return {'ready':not blockers,'blockers':blockers,'active_campaign':campaign[0] if campaign else None,
            'active_mission':mission[0] if mission else None,'pending':pending,'remaining':remaining,'locked':bool(locked)}

def status(c,cfg=None,cid=None):
    p=_campaign(c,cid) if cid is not None else c.execute('SELECT * FROM campaigns ORDER BY id DESC LIMIT 1').fetchone()
    if not p:return None
    d=dict(p);d['permissions']=json.loads(d['permissions'])
    d['spent']=costs(c,p['id']);d['searches']=searches(c,p['id']);d['missions']=[dict(x) for x in _missions(c,p['id'])]
    d['recovery_kind']=recovery_kind(c,d['missions'][-1]['id'],cfg) if cfg and p['state']=='bloqué' and d['missions'] else None
    d['recoverable']=bool(d['recovery_kind'])
    d['incident_recoveries']=incidents.history(c,p['id'])
    d['commercial_recoveries']=[dict(x) for x in c.execute('SELECT cr.* FROM commercial_recoveries cr JOIN campaign_missions cm ON cm.mission=cr.mission WHERE cm.campaign=? ORDER BY cr.task',(p['id'],))]
    d['connectors']=connectors.campaign_status(c,p['id'])
    d['laboratory']=[laboratory.summary_row(r) for r in c.execute('SELECT * FROM laboratory_runs WHERE campaign=?',(p['id'],))]
    scope=portfolio.scope(c,p['id'])
    d['project']=scope['project'] if scope else None;d['scope']=scope['scope'] if scope else 'legacy'
    cy=improvement.cycle(c,p['id']);d['improvement']=improvement.summary(c,cy) if cy else None
    return d

def start(c,body,cfg):
    if body.get('confirm') is not True:raise ValueError('Autorisation initiale explicite requise')
    if active(c) or c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone():raise ValueError('Un travail est déjà en cours')
    if c.execute("SELECT 1 FROM requests WHERE state='en attente'").fetchone():raise ValueError('Traiter les décisions en attente avant une campagne')
    goal=body.get('goal');count=body.get('max_missions');flags=body.get('permissions');cap=body.get('search_cap',0)
    if not isinstance(goal,str) or not 1<=len(goal.strip())<=600:raise ValueError('Objectif de 1 à 600 caractères requis')
    if type(count) is not int or not 1<=count<=10:raise ValueError('1 à 10 missions maximum')
    if not isinstance(flags,dict) or set(flags)!=set(FLAGS) or any(type(v) is not bool for v in flags.values()) or not any(flags.values()):raise ValueError('Autorisations invalides')
    if type(cap) is not int or not 0<=cap<=10 or cap and (not flags['research'] or not cfg['brave']):raise ValueError('Quota Brave invalide ou non configuré')
    raw=body.get('budget')
    if not isinstance(raw,str) or len(raw)>12:raise ValueError('Budget décimal requis')
    try:
        d=Decimal(raw);micro=d*1000000
        if not d.is_finite() or not Decimal('0.01')<=d<=Decimal('10') or micro!=micro.to_integral_value():raise ValueError('Budget entre 0,01 et 10 USD requis')
        budget=int(micro)
    except (InvalidOperation,ValueError,OverflowError):raise ValueError('Budget invalide')
    remaining=cfg['budget']-accounting.global_total(c)
    if not cfg['key'] or budget>remaining:raise ValueError('Clé ou budget global disponible insuffisant')
    portfolio.sync(c)
    requested=body.get('project')
    explicit=body.get('campaign_mode')
    if 'campaign_mode' in body:
        if explicit not in ('progression','explore','international','commercial','improvement'):raise ValueError('Mode de campagne inconnu')
        if (explicit=='commercial')!=('commercial' in body) or (explicit=='improvement')!=('improvement' in body):raise ValueError('Mode et action incohérents')
        if explicit in ('explore','international') and requested!='explore':raise ValueError('Exploration : sélection explore requise')
        if explicit=='progression' and requested=='explore':raise ValueError('Sélectionner explicitement le mode exploration')
        if explicit=='international' and (body.get('connector_selection')!=[ 'worldbank.market','n8n.market_compare'] or count!=1):raise ValueError('Étude internationale : deux connecteurs précis et une mission requis')
    # Old API clients and already-authorized campaigns retain their original scope.
    frozen=None
    if 'commercial' in body:
        if (body['commercial'] is not True or 'improvement' in body or type(requested) is not int or count!=1 or not flags['market'] or flags['production'] or body.get('connector_cap',0)):
            raise ValueError('Préparation commerciale : activité précise, une mission, marché autorisé, production et connecteurs désactivés')
        project=portfolio.project(c,requested)
        if not project or project['state']!='active':raise ValueError('Activité inactive ou inconnue')
        pid=requested;scope='commercial';artifact=portfolio.latest(c,pid);source=artifact['id'] if artifact else None
    elif 'improvement' in body:
        mode=body['improvement']
        if type(requested) is not int or not flags['production'] or not flags['tests'] or cap or count!=1:
            raise ValueError('Amélioration : activité précise, production et tests, une mission, Brave 0 requis')
        project=portfolio.project(c,requested)
        if not project or project['state']!='active':raise ValueError('Activité inactive ou inconnue')
        pid=requested;scope='improvement';artifact=portfolio.latest(c,pid)
        frozen=improvement.plan(c,artifact,mode)
        source=artifact['id']
    elif 'project' in body:
        pid,scope=portfolio.select(c,requested,flags)
        artifact=portfolio.latest(c,pid) if pid is not None else None
        source=artifact['id'] if artifact else None
    else:
        row=c.execute("""SELECT a.id FROM artifacts a JOIN missions m ON m.id=a.mission
            WHERE m.mode='cloud' AND m.state='terminée' AND a.agent='NEXUS' AND NOT EXISTS(SELECT 1 FROM campaign_missions cm JOIN improvement_cycles ic ON ic.campaign=cm.campaign WHERE cm.mission=a.mission) ORDER BY a.id DESC LIMIT 1""").fetchone()
        source=row[0] if row else None
    cid=c.execute("""INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,source,state)
        VALUES(?,?,?,?,?,?,'actif')""",(goal.strip(),budget,count,json.dumps(flags),cap,source)).lastrowid
    if 'project' in body:c.execute('INSERT INTO campaign_projects(campaign,project,scope) VALUES(?,?,?)',(cid,pid,scope))
    if 'commercial_followup' in body:
        if scope!='commercial' or not cap or not flags['research'] or not flags['tests'] or not cfg['mission_search_limit'] or c.execute('SELECT COUNT(*) FROM searches').fetchone()[0]>=cfg['limit']:raise ValueError('Complément : recherche et revue autorisées, quota Brave réellement disponible requis')
        commercial.authorize_followup(c,cid,pid,source,body['commercial_followup'])
    connectors.authorize_campaign(c,cid,body)
    if frozen is not None:improvement.begin(c,cid,pid,artifact,mode,goal.strip(),frozen)
    return cid

def stop(c,cid):
    p=_campaign(c,cid)
    if not p or p['state']!=ACTIVE:raise ValueError('Campagne non active')
    c.execute("UPDATE campaigns SET state='arrêté',reason='Arrêt demandé. Un appel déjà engagé peut être facturé.' WHERE id=?",(cid,))
    c.execute("""UPDATE missions SET state='arrêtée',error='Autopilote arrêté par le propriétaire'
        WHERE state='en cours' AND id IN (SELECT mission FROM campaign_missions WHERE campaign=?)""",(cid,))

def resume(c,cid,cfg):
    p=_campaign(c,cid)
    if not p or p['state'] not in ('interrompu','arrêté','en attente','bloqué'):raise ValueError('Campagne non reprenable automatiquement')
    if active(c) or c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone():raise ValueError('Un travail est déjà en cours')
    if c.execute("SELECT 1 FROM requests WHERE state='en attente'").fetchone():raise ValueError('Traiter les décisions en attente')
    if not cfg['key'] or costs(c,cid)>=p['budget'] or accounting.global_total(c)>=cfg['budget']:raise ValueError('Ressources insuffisantes; aucune remise à zéro')
    scope=portfolio.scope(c,cid)
    if scope and scope['project'] is not None and portfolio.project(c,scope['project'])['state']!='active':raise ValueError('Réactiver cette activité avant la reprise')
    cy=improvement.cycle(c,cid)
    if cy and (cy['state']!='pending' or improvement.pinned(c,cy['project'])['id']!=cy['baseline']):raise ValueError('Cycle remplacé ou référence modifiée')
    ms=_missions(c,cid)
    kind=recovery_kind(c,ms[-1]['id'],cfg) if p['state']=='bloqué' and ms else None
    recover=bool(kind)
    if kind=='transient':incidents.record(c,ms[-1]['id'],cfg)
    if kind=='commercial':
        tid=commercial.recovery_task(c,ms[-1]['id'],cfg)
        c.execute('INSERT INTO commercial_recoveries(task,mission) VALUES(?,?)',(tid,ms[-1]['id']))
    if p['state']=='bloqué' and not recover:raise ValueError('Blocage non récupérable sans diagnostic; aucun compteur réinitialisé')
    if ms and (recover or ms[-1]['state'] in ('interrompue','arrêtée','en attente','prête')):
        c.execute("UPDATE missions SET state='en cours',error='' WHERE id=?",(ms[-1]['id'],))
    elif ms and ms[-1]['state']!='terminée':raise ValueError('Mission bloquée; diagnostic requis')
    c.execute("UPDATE campaigns SET state='actif',reason='' WHERE id=?",(cid,))

def _proof(c,artifact,mid):
    rows=list(c.execute("""SELECT v.result,v.spec,a.content FROM verification_results v JOIN artifacts a ON a.id=v.artifact
        WHERE v.artifact=? AND v.mission=? AND v.agent='SENTINEL' ORDER BY v.id""",(artifact,mid)))
    states=[]
    previous=[]
    for x in c.execute('SELECT spec,result FROM verification_results WHERE artifact=? AND mission<?',(artifact,mid)):
        try:
            if json.loads(x['result']).get('status') in ('passed','failed'):previous.append(json.loads(x['spec']))
        except (ValueError,TypeError,AttributeError):continue
    for r in rows:
        result=json.loads(r['result'])
        if result.get('sha256')!=hashlib.sha256(r['content'].encode()).hexdigest():continue
        checks=result.get('checks',[])
        if result.get('status')=='passed':
            if not checks or not all(x.get('passed') is True for x in checks):states.append('invalid')
            elif json.loads(r['spec']) not in previous:states.append('passed')
        elif result.get('status') not in ('invalid','unavailable'):states.append(result.get('status'))
    if 'failed' in states:return 'failed'
    return 'passed' if states and all(x=='passed' for x in states) else 'missing'

def choose(c,p):
    """One bounded action based on durable results; no text report is a commercial proof."""
    cid=p['id'];flags=json.loads(p['permissions']);ms=_missions(c,cid);kinds={x['kind'] for x in ms}
    scoped=portfolio.scope(c,cid)
    if scoped:
        if scoped['scope']=='draft_recovery':
            import draft_recovery
            return draft_recovery.choose(c,cid),'Audit de récupération borné.'
        if scoped['scope']=='commercial':
            return (('commercial',p['source'],None),'') if not ms else (None,'Préparation commerciale terminée; aucun test externe autorisé.')
        if scoped['scope']=='improvement':
            return (('improve',p['source'],None),'') if not ms else (None,'Production candidate terminée.')
        if scoped['scope']=='explore':
            return ((('opportunity',None,None),'') if not ms and flags['research'] else (None,'Exploration terminée; sélectionner une activité pour la suite.'))
        return portfolio.next_step(c,scoped['project'],flags)
    artifact=p['source']
    for x in ms:
        if x['kind'] in ('create','improve'):
            row=c.execute("SELECT id FROM artifacts WHERE mission=? AND agent='NEXUS' ORDER BY id DESC LIMIT 1",(x['id'],)).fetchone()
            if not row:return None,'Production sans fichier NEXUS; diagnostic requis.'
            artifact=row['id']
    audited=[x for x in ms if x['kind']=='functional' and x['artifact']==artifact]
    if audited:
        verdict=_proof(c,artifact,audited[-1]['id'])
        if verdict=='failed':
            if flags['production'] and 'improve' not in kinds:return ('improve',artifact,None),''
            return None,'Tests échoués; correction supplémentaire non autorisée ou déjà tentée.'
        if verdict!='passed':return None,'Audit sans nouvelle preuve fonctionnelle exploitable; diagnostic requis.'
        if flags['market'] and 'market' not in kinds:return ('market',artifact,None),''
    elif artifact and flags['tests']:
        a=c.execute('SELECT name FROM artifacts WHERE id=?',(artifact,)).fetchone()
        if a and a['name'].lower().endswith(('.html','.csv','.json')):return ('functional',artifact,None),''
        return None,'Format sans vérificateur fonctionnel; examen nécessaire.'
    if flags['research'] and 'opportunity' not in kinds:return ('opportunity',None,None),''
    if flags['production'] and 'create' not in kinds:
        for opp in c.execute("""SELECT o.id,o.title FROM opportunities o JOIN campaign_missions cm ON cm.mission=o.mission
            WHERE cm.campaign=? AND cm.kind='opportunity' ORDER BY o.id DESC""",(cid,)):
            if not portfolio.economic_hold(c,opp['id']):return ('create',None,dict(opp)),''
    return None,'Aucune nouvelle étape autorisée et fondée sur les résultats disponibles.'

def title(p,kind,artifact,opp):
    tasks={
      'commercial':"ORION : si recherche autorisée, lire des pages sectorielles via Brave, enregistrer des citations exactes avec commercial_signal; sinon signaler les lacunes. HERMES : commercial_offer, offre et protocole futur mesurable, signal_ids pertinents ou vides. MIDAS : commercial_economics sur l’ID de l’offre. SENTINEL si tests autorisés : commercial_review après MIDAS. ATLAS : synthèse factuelle, aucune publication, prospection, vente ou dépense commerciale. Réutilise les preuves de l’activité sans inventer de rapprochement.",
      'opportunity':"ORION puis MIDAS : explore des secteurs légaux diversifiés. Si autorisés, worldbank.market compare 2–3 pays (population, internet, PIB/hab.), n8n.market_compare exploite le relevé de la mission. ORION enregistre des opportunités via opportunity; MIDAS évalue chaque ID via assess_opportunity en EUR ou explique les omissions. ATLAS s’appuie sur le registre collectif; SENTINEL si anomalies, tests autorisés et budget suffisant. Macro ≠ demande; concurrence et coûts non prouvés restent hypothèses. Aucun achat.",
      'create':"NEXUS : à partir de l’opportunité #"+str((opp or {}).get('id','?'))+" ("+str((opp or {}).get('title',''))[:160]+"), crée un petit livrable autonome interne, testable en HTML/CSV/JSON. Utilise la mémoire pour les éléments disponibles. Expérience proposée : "+str((opp or {}).get('next_test',''))[:300]+". Produis un livrable et des données synthétiques avec résultats attendus; ne prétends pas que la demande est validée.",
      'improve':"NEXUS : corrige uniquement les défauts observés dans la preuve du fichier ref:"+str(artifact)+", produis un fichier distinct, ne modifie pas l’original.",
      'functional':"SENTINEL : lis ref:"+str(artifact)+", examine les preuves antérieures, définis des assertions indépendantes sur les lacunes et exécute test_file sur ce fichier exact. Ne répète pas les tests déjà passés sans nécessité. Adapte les tests au produit et à ses critères enregistrés; distingue assertions synthétiques, performance mesurée et critères non couverts.",
      'market':"HERMES et MIDAS : étudie la demande, les alternatives, prix hypothétiques, coûts et seuils, pour ref:"+str(artifact)+". Les preuves techniques sont bornées. Aucun contact client, publication ou vente. Distingue données et hypothèses."}
    return ("AUTOPILOTE — "+kind+" | Objectif propriétaire : "+p['goal']+" | ATLAS, délègue aux agents autorisés : "+tasks[kind]+
            " Rapports courts, outils autorisés seulement, aucune dépense commerciale ni action externe hors recherche autorisée. Termine avec limites et preuves.")[:1500]

def worker(s,cid):
    # Hold the existing global worker lock across all missions; no polling scheduler.
    with s.LOCK:
        try:
            while True:
                cfg=s.config(); lab_artifact=None; compare_mid=None
                with s.db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    p=_campaign(c,cid)
                    if not p or p['state']!=ACTIVE:return
                    import periodic
                    periodic.guard_campaign(c,cid)
                    ms=_missions(c,cid);last=ms[-1] if ms else None
                    if last and last['state']=='en cours':mid=last['id']
                    else:
                        if last and last['state']!='terminée':
                            state='en attente' if last['state']=='en attente' else 'bloqué'
                            c.execute('UPDATE campaigns SET state=?,reason=? WHERE id=?',(state,last['error'] or last['state'],cid));return
                        if c.execute("SELECT 1 FROM requests WHERE state='en attente'").fetchone():
                            c.execute("UPDATE campaigns SET state='en attente',reason='Décision requise.' WHERE id=?",(cid,));return
                        cy=improvement.cycle(c,cid)
                        if cy and last and last['state']=='terminée':compare_mid=last['id']
                        if compare_mid is not None:pass
                        elif len(ms)>=p['max_missions']:
                            c.execute("UPDATE campaigns SET state='terminé',reason='Nombre maximal de missions atteint; aucun objectif commercial certifié.' WHERE id=?",(cid,));return
                        if compare_mid is None:
                            if not cfg['key'] or costs(c,cid)>=p['budget'] or s.used(c)>=cfg['budget']:
                                c.execute("UPDATE campaigns SET state='terminé',reason='Plafond logiciel ou ressource atteint.' WHERE id=?",(cid,));return
                            portfolio.sync(c)
                            nxt,reason=choose(c,p)
                            if not nxt:
                                c.execute("UPDATE campaigns SET state='terminé',reason=? WHERE id=?",(reason,cid));return
                            kind,artifact,opp=nxt
                            planned=c.execute("SELECT kind,artifact FROM enterprise_plan_queue WHERE campaign=?",(cid,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_plan_queue'").fetchone() else None
                            if planned and (planned['kind']!=kind or planned['artifact']!=artifact):
                                c.execute("UPDATE campaigns SET state='terminé',reason='Étape initiale achevée ou différente; réévaluation par le planificateur.' WHERE id=?",(cid,));return
                            if kind=='laboratory':
                                if c.execute('SELECT 1 FROM laboratory_runs WHERE campaign=?',(cid,)).fetchone():
                                    c.execute("UPDATE campaigns SET state='terminé',reason='Une expérience locale maximum par campagne; examiner les résultats.' WHERE id=?",(cid,));return
                                lab_artifact=artifact
                            else:
                                follow=commercial.followup(c,cid) if kind=='commercial' else None
                                mission_title=improvement.production_title(cy,improvement.row(c,artifact)) if cy else title(p,kind,artifact,opp)
                                if scoped_recovery := portfolio.scope(c,cid):
                                    if scoped_recovery['scope']=='draft_recovery':
                                        mission_title=('AUDIT DE RÉCUPÉRATION — fichier exact ref:'+str(artifact)+' ; ATLAS délègue SENTINEL pour lire et tester ce brouillon sans le modifier. Assertions indépendantes sur critères enregistrés, données fictives, aucune publication. Un contrôle statique ne suffit pas. Rapports courts et honnêtes.')
                                if follow:mission_title=("COMPLÉMENT DOCUMENTAIRE — offre #"+str(follow['base_offer'])+" ; ATLAS délègue ORION pour rechercher les besoins acheteurs et alternatives/prix, lire les pages et enregistrer de nouveaux commercial_signal. Puis SENTINEL seulement pour commercial_extend sur l’offre historique : conserver les signaux précédents, ajouter les nouveaux indices exploitables, réviser risques et revue. Aucun nouveau prix, protocole, calcul MIDAS ou offre HERMES. Si aucun nouvel indice exploitable, terminer sans nouvelle offre. Aucun lancement externe.")
                                mid=s.moteur.create(s,c,mission_title,'cloud',artifact_id=artifact)
                                c.execute('INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,?,?)',(cid,mid,kind,artifact))
                                scoped=portfolio.scope(c,cid)
                                if scoped and scoped['project'] is not None:portfolio.attach(c,mid,scoped['project'],'campagne ciblée')
                if compare_mid is not None:
                    improvement.complete(s,cid,compare_mid,cfg);return
                if lab_artifact is not None:
                    result=laboratory.run(s,lab_artifact,laboratory.PROFILE,300,laboratory.DEFAULT_SEED,cfg,campaign=cid)
                    if result['status']!='passed':
                        with s.db() as c:c.execute("UPDATE campaigns SET state='terminé',reason=? WHERE id=? AND state='actif'",('Banc d’essai '+result['status']+'; examiner le laboratoire avant toute suite.',cid))
                        return
                    with s.db() as c:
                        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_plan_queue'").fetchone() and c.execute('SELECT 1 FROM enterprise_plan_queue WHERE campaign=?',(cid,)).fetchone():
                            c.execute("UPDATE campaigns SET state='terminé',reason='Banc d’essai unique terminé; réévaluation par le planificateur.' WHERE id=? AND state='actif'",(cid,));return
                    continue
                s.moteur.run(s,mid)
                with s.db() as c:portfolio.sync(c)
        except Exception as e:
            with s.db() as c:
                c.execute("UPDATE campaigns SET state='bloqué',reason=? WHERE id=? AND state='actif'",(str(e)[:400],cid))
                c.execute("""UPDATE missions SET state='bloquée',error='Erreur Autopilote; diagnostic requis'
                    WHERE state='en cours' AND id IN (SELECT mission FROM campaign_missions WHERE campaign=?)""",(cid,))
