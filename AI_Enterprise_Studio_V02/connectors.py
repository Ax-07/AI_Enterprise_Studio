"""Trusted capability registry. Default deny, bounded public read-only adapters."""
import hashlib,http.client,json,os,re,ssl,secrets
import n8n_bridge as n8n
import intelligence as intel
from decimal import Decimal,InvalidOperation

AGENTS=('ATLAS','ORION','MIDAS','NEXUS','HERMES','SENTINEL','PROMETHEUS','MNEMOS')
PUBLIC='github.public_repo'
LIMIT='Quotas cumulés locaux, distincts d’OpenAI et Brave. Coût réservé par tarif fixe approuvé, pas une facture. Aucun achat ni écriture externe.'
MAX_RESPONSE=65536
REGISTRY={
 PUBLIC:{'label':'GitHub — dépôt public','description':'Métadonnées publiques : activité, licence, langage, étoiles. Aucun contenu privé ni écriture.',
         'provider':'GitHub','available':True,'risk':'public_read','method':'GET','cost_usd_micro':0,
         'roles':('ATLAS','ORION','MIDAS','HERMES','SENTINEL','NEXUS','PROMETHEUS'),'secret_env':None},
 'n8n.workflow':{'label':'n8n — workflow autorisé','description':'Contrat préparé; aucun endpoint, webhook ou workflow exécutable dans cette version.',
         'provider':'n8n','available':False,'risk':'not_enabled','method':None,'cost_usd_micro':None,
         'roles':(),'secret_env':'AES_N8N_TOKEN'},
 n8n.HEALTH:{'label':'n8n — Test de communication','description':'Vérifie le contrat du webhook local authentifié; aucun effet commercial.', 'provider':'n8n','available':True,'risk':'local_compute','method':'POST','cost_usd_micro':0,'roles':n8n.ROLES,'secret_env':'AES_N8N_TOKEN','revision':1},
 intel.CAP:{'label':'Banque mondiale — Marchés internationaux','description':'Population, internet et PIB par habitant de deux ou trois pays sur une même année. Source publique officielle, pas de preuve de demande.', 'provider':'World Bank','available':True,'risk':'public_read','method':'GET','cost_usd_micro':0,'roles':('ORION','MIDAS','ATLAS','HERMES','SENTINEL'),'secret_env':None,'revision':1},
 n8n.COMPARE:{'label':'n8n — Comparaison de marchés','description':'Estimation comparative des internautes à partir d’un relevé Banque mondiale de la mission; aucune donnée client.', 'provider':'n8n','available':True,'risk':'local_compute','method':'POST','cost_usd_micro':0,'roles':('ORION','MIDAS','ATLAS','HERMES','SENTINEL'),'secret_env':'AES_N8N_TOKEN','revision':1},
 n8n.METRICS:{'label':'n8n — Statistiques numériques','description':'Compte, somme, minimum, maximum de 1 à 100 entiers. Aucun appel fournisseur ni donnée client.', 'provider':'n8n','available':True,'risk':'local_compute','method':'POST','cost_usd_micro':0,'roles':n8n.ROLES,'secret_env':'AES_N8N_TOKEN','revision':1},
}

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS connector_policies(
        capability TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, agents TEXT NOT NULL DEFAULT '[]',
        max_calls INTEGER NOT NULL DEFAULT 0, budget INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS connector_campaigns(
        campaign INTEGER PRIMARY KEY REFERENCES campaigns(id), max_calls INTEGER NOT NULL, budget INTEGER NOT NULL,
        capabilities TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS connector_runs(
        id INTEGER PRIMARY KEY, capability TEXT NOT NULL, mission INTEGER REFERENCES missions(id),
        task INTEGER REFERENCES tasks(id), campaign INTEGER REFERENCES campaigns(id),
        actor TEXT NOT NULL, input_sha256 TEXT NOT NULL, reserved INTEGER NOT NULL,
        state TEXT NOT NULL, diagnostic TEXT NOT NULL DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP,
        finished TEXT);
        CREATE INDEX IF NOT EXISTS connector_runs_cap ON connector_runs(capability,id);
        CREATE INDEX IF NOT EXISTS connector_runs_campaign ON connector_runs(campaign,id);
        CREATE INDEX IF NOT EXISTS connector_runs_mission ON connector_runs(mission,id);
        CREATE TABLE IF NOT EXISTS connector_workflow_results(
          run INTEGER PRIMARY KEY REFERENCES connector_runs(id), request_id TEXT NOT NULL UNIQUE,
          execution_id TEXT, result TEXT);""")
    intel.init(c)
    for cap in REGISTRY:c.execute('INSERT OR IGNORE INTO connector_policies(capability) VALUES(?)',(cap,))
    # A crash after reservation never releases a potentially consumed quota.
    c.execute("UPDATE connector_runs SET state='unknown',diagnostic='Interruption; réservation conservée' WHERE state='reserved'")

def micro(raw):
    if not isinstance(raw,str) or len(raw)>12:raise ValueError('Budget connecteurs décimal requis')
    try:
        n=Decimal(raw)*1000000
        if not n.is_finite() or n!=n.to_integral_value() or not 0<=n<=10000000:raise ValueError('Budget connecteurs entre 0 et 10 USD')
        return int(n)
    except (InvalidOperation,OverflowError,ValueError):raise ValueError('Budget connecteurs invalide') from None

def totals(c,where='',args=()):
    n,sp=c.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0) FROM connector_runs '+where,args).fetchone()
    return {'calls':n,'reserved':sp}

def policy(c,cap):
    r=c.execute('SELECT * FROM connector_policies WHERE capability=?',(cap,)).fetchone()
    if not r:raise ValueError('Capacité inconnue')
    return {**dict(r),'agents':json.loads(r['agents']),'enabled':bool(r['enabled'])}

def usable(cap):
    spec=REGISTRY[cap]
    return spec['available'] and (cap not in n8n.PATHS or n8n.configured())

def set_policy(c,body):
    cap=body.get('capability')
    if not isinstance(cap,str) or cap not in REGISTRY:raise ValueError('Capacité inconnue')
    spec=REGISTRY[cap];enabled=body.get('enabled');roles=body.get('agents');count=body.get('max_calls')
    budget=micro(body.get('budget'))
    if type(enabled) is not bool or not isinstance(roles,list) or any(not isinstance(x,str) or x not in spec['roles'] for x in roles) or len(set(roles))!=len(roles):
        raise ValueError('Permissions invalides')
    if type(count) is not int or not 0<=count<=1000:raise ValueError('Quota de 0 à 1000 tentatives')
    if enabled and (not usable(cap) or spec['cost_usd_micro'] is None or count==0 or budget<spec['cost_usd_micro']):
        raise ValueError('Capacité indisponible ou sans tarif/quota approuvé')
    if c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone() or c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone():
        raise ValueError('Arrêter le travail actif avant de modifier les permissions')
    c.execute('UPDATE connector_policies SET enabled=?,agents=?,max_calls=?,budget=? WHERE capability=?',
        (int(enabled),json.dumps(sorted(roles)),count,budget,cap))

def authorize_campaign(c,cid,body):
    count=body.get('connector_cap',0);budget=micro(body.get('connector_budget','0'))
    if type(count) is not int or not 0<=count<=10:raise ValueError('Quota connecteurs entre 0 et 10')
    if not count:
        if budget:raise ValueError('Budget connecteurs sans quota')
        return
    if 'project' not in body or not body['permissions']['research'] or 'improvement' in body:
        raise ValueError('Connecteurs : campagne ciblée de recherche (hors amélioration) requise')
    caps={}
    for cap,spec in REGISTRY.items():
        p=policy(c,cap);t=totals(c,'WHERE capability=?',(cap,))
        if p['enabled'] and p['agents'] and usable(cap) and spec['risk'] in ('public_read','local_compute') and spec['cost_usd_micro'] is not None and t['calls']<p['max_calls'] and t['reserved']+spec['cost_usd_micro']<=p['budget'] and spec['cost_usd_micro']<=budget:
            caps[cap]={'agents':p['agents'],'cost':spec['cost_usd_micro'],'revision':spec.get('revision',1)}
    if not caps:raise ValueError('Aucun connecteur autorisé avec quota et budget disponibles')
    c.execute('INSERT INTO connector_campaigns(campaign,max_calls,budget,capabilities) VALUES(?,?,?,?)',
        (cid,count,budget,json.dumps(caps)))

def campaign_status(c,cid):
    r=c.execute('SELECT * FROM connector_campaigns WHERE campaign=?',(cid,)).fetchone()
    if not r:return {'max_calls':0,'budget':0,'calls':0,'reserved':0,'capabilities':[],'grants':{}}
    grants=json.loads(r['capabilities'])
    return {**dict(r),'capabilities':list(grants),'grants':grants,**totals(c,'WHERE campaign=?',(cid,))}

def check(c,cap,mid,tid,actor):
    spec=REGISTRY.get(cap)
    if not spec or not usable(cap) or spec['risk'] not in ('public_read','local_compute') or type(spec['cost_usd_micro']) is not int or spec['cost_usd_micro']<0:
        raise ValueError('Capacité non disponible ou tarif non approuvé')
    p=policy(c,cap);t=totals(c,'WHERE capability=?',(cap,));cost=spec['cost_usd_micro']
    if not p['enabled']:raise ValueError('Connecteur désactivé')
    if t['calls']>=p['max_calls'] or t['reserved']+cost>p['budget']:raise ValueError('Quota ou budget du connecteur atteint')
    if actor=='PROPRIETAIRE':
        if mid is not None or tid is not None:raise ValueError('Contexte propriétaire invalide')
        if c.execute("SELECT 1 FROM missions WHERE state='en cours'").fetchone() or c.execute("SELECT 1 FROM campaigns WHERE state='actif'").fetchone():raise ValueError('Travail en cours')
        return None,cost
    if actor not in spec['roles'] or actor not in p['agents']:raise ValueError('Agent non autorisé pour ce connecteur')
    task=c.execute("""SELECT t.agent,t.state,m.mode,m.state AS mission_state FROM tasks t
        JOIN missions m ON m.id=t.mission WHERE t.id=? AND t.mission=?""",(tid,mid)).fetchone()
    if not task or task['agent']!=actor or task['state']!='prête' or task['mode']!='cloud' or task['mission_state']!='en cours':raise ValueError('Tâche Cloud active requise')
    cy=c.execute("""SELECT c.id,c.state,c.permissions,cm.kind FROM campaigns c JOIN campaign_missions cm ON cm.campaign=c.id
        WHERE cm.mission=?""",(mid,)).fetchone()
    if not cy or cy['state']!='actif' or cy['kind'] not in ('opportunity','market') or not json.loads(cy['permissions'])['research']:
        raise ValueError('Campagne de recherche explicitement autorisée requise')
    cc=campaign_status(c,cy['id'])
    grant=cc['grants'].get(cap)
    if not grant or actor not in grant['agents'] or cost!=grant['cost'] or grant.get('revision',1)!=spec.get('revision',1) or cc['calls']>=cc['max_calls'] or cc['reserved']+cost>cc['budget']:
        raise ValueError('Quota ou budget de campagne connecteurs atteint')
    if totals(c,'WHERE mission=?',(mid,))['calls']>=3:raise ValueError('Plafond de trois appels connecteurs par mission')
    return cy['id'],cost

def available(c,t):
    out=[]
    for cap in REGISTRY:
        try:
            check(c,cap,t['mission'],t['id'],t['agent'])
            if cap==n8n.COMPARE:
                candidates=intel.sources(c,t['mission'])
                if not any(intel.comparable(x['snapshot']) for x in candidates):continue
        except ValueError:continue
        out.append(cap)
    return out

def slug(text):
    if not isinstance(text,str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}',text) or '..' in text or text.split('/')[1] in ('.','-') or text.lower().endswith('.git'):
        raise ValueError('Dépôt public au format propriétaire/dépôt, sans URL ni paramètres')
    return text

def github_repo(name):
    """No credentials, redirects, model-selected host, arbitrary path, proxy or payload."""
    name=slug(name)
    conn=http.client.HTTPSConnection('api.github.com',443,timeout=8,context=ssl.create_default_context())
    try:
        conn.request('GET','/repos/'+name,headers={'Accept':'application/vnd.github+json','User-Agent':'AI-Enterprise-Studio/0.4.0','X-GitHub-Api-Version':'2026-03-10','Connection':'close'})
        resp=conn.getresponse()
        if resp.status!=200:raise RuntimeError('HTTP '+str(resp.status))
        raw=resp.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:raise RuntimeError('Réponse trop volumineuse')
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('private') is not False or not isinstance(data.get('full_name'),str) or data['full_name'].lower()!=name.lower():
            raise RuntimeError('Réponse publique non confirmée')
        def integer(k):
            x=data.get(k);return x if type(x) is int and 0<=x<=2**53-1 else None
        def short(x):
            return x[:100] if isinstance(x,str) else None
        license_data=data.get('license')
        return {'repository':name,'url':'https://github.com/'+name,'stars':integer('stargazers_count'),
            'forks':integer('forks_count'),'open_issues_and_prs':integer('open_issues_count'),
            'language':short(data.get('language')),'license':short(license_data.get('spdx_id')) if isinstance(license_data,dict) else None,
            'updated_at':short(data.get('updated_at')),'pushed_at':short(data.get('pushed_at')),
            'archived':data.get('archived') is True,'note':'Métadonnées publiques non certifiées; popularité ≠ demande commerciale.'}
    finally:conn.close()

ADAPTERS={PUBLIC:github_repo,intel.CAP:intel.fetch}

def validate_input(cap,text):
    if cap==PUBLIC:return slug(text)
    if cap==intel.CAP:return intel.request_spec(text)
    if cap==n8n.COMPARE:return intel.compare_ref(text)
    if cap in n8n.PATHS:return n8n.validate(cap,text)
    raise ValueError('Connecteur non exécutable')

def invoke(s,cap,text,mid=None,tid=None,actor='PROPRIETAIRE'):
    if not isinstance(cap,str):raise ValueError('Connecteur non exécutable')
    value=validate_input(cap,text);is_n8n=cap in n8n.PATHS
    digest=hashlib.sha256(value.encode()).hexdigest();request_id=secrets.token_hex(16) if is_n8n else None
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        cid,cost=check(c,cap,mid,tid,actor)
        if cap==n8n.COMPARE:
            payload=intel.compare_input(c,value,mid) if mid is not None else n8n.SAMPLE_COMPARE
        else:payload=value
        if (is_n8n or cap==intel.CAP) and mid is not None and c.execute('SELECT 1 FROM connector_runs WHERE mission=? AND capability=? AND input_sha256=?',(mid,cap,digest)).fetchone():raise ValueError('Workflow identique déjà tenté; consulter le journal, aucun retry automatique')
        rid=c.execute("""INSERT INTO connector_runs(capability,mission,task,campaign,actor,input_sha256,reserved,state)
            VALUES(?,?,?,?,?,?,?,'reserved')""",(cap,mid,tid,cid,actor,digest,cost)).lastrowid
        if is_n8n:c.execute('INSERT INTO connector_workflow_results(run,request_id) VALUES(?,?)',(rid,request_id))
    try:
        result=n8n.call(cap,payload,request_id) if is_n8n else ADAPTERS[cap](value)
    except Exception as e:
        # No exception messages, response bodies, headers, or secrets are logged.
        diag=type(e).__name__
        if isinstance(e,RuntimeError) and re.fullmatch(r'HTTP [1-5][0-9]{2}',str(e)):diag=str(e)
        elif isinstance(e,n8n.Unconfirmed) and str(e) in ('Réponse trop volumineuse','Contrat de réponse invalide','Résultat incohérent','TimeoutError','ConnectionRefusedError','RemoteDisconnected','ConnectionResetError'):diag=str(e)
        state='unknown' if is_n8n else 'failed'
        with s.db() as c:c.execute('UPDATE connector_runs SET state=?,diagnostic=?,finished=CURRENT_TIMESTAMP WHERE id=?',(state,diag,rid))
        return {'connector':cap,'run':rid,'status':state,'diagnostic':diag,'note':'Tentative décomptée; aucun retry automatique.'}
    if cap==n8n.COMPARE:result={**result,'source_run':json.loads(value)['source_run'] if mid is not None else None,'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'note':'Proxy de couverture numérique, pas demande; test propriétaire synthétique si source_run null.'}
    with s.db() as c:
        if cap==intel.CAP:intel.record(c,rid,result)
        if is_n8n:c.execute('UPDATE connector_workflow_results SET execution_id=?,result=? WHERE run=?',(result['execution_id'],json.dumps(result,ensure_ascii=False),rid))
        c.execute("UPDATE connector_runs SET state='received',finished=CURRENT_TIMESTAMP WHERE id=?",(rid,))
    return {'connector':cap,'run':rid,'status':'received','data':result}

def status(c):
    caps=[]
    for cap,spec in REGISTRY.items():
        # Do not read, copy or return credential values; only presence of a future env variable.
        caps.append({'id':cap,**{k:v for k,v in spec.items() if k!='secret_env'},
            'available':usable(cap),'credential_present':bool(spec['secret_env'] and os.environ.get(spec['secret_env'])),
            'policy':policy(c,cap),**totals(c,'WHERE capability=?',(cap,))})
    return {'capabilities':caps,'runs':[dict(r) for r in c.execute('SELECT r.*,w.request_id,w.execution_id,w.result AS workflow_result FROM connector_runs r LEFT JOIN connector_workflow_results w ON w.run=r.id ORDER BY r.id DESC LIMIT 100')],
            'total':totals(c),'limit':LIMIT}
