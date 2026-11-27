"""Owner-only local commercial registry. No agent actions, contacts, publication or payment API."""
import hashlib,json,re,time
import commercial,portfolio
from departments import receipt_accounting

LIMIT='Registre local uniquement. Observations volontaires attestées par le propriétaire, non vérifiées par un tiers. Aucune prospection, publication, transaction, livraison ni dépense externe autorisée. Paiements test et déclarations propriétaire séparés; revenus vérifiés indisponibles avant intégration d’un prestataire.'
def now():return int(time.time())
def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS business_trials(
        id INTEGER PRIMARY KEY,offer INTEGER NOT NULL UNIQUE REFERENCES commercial_offers(id),
        project INTEGER NOT NULL REFERENCES projects(id),artifact INTEGER NOT NULL REFERENCES artifacts(id),
        snapshot TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,metric TEXT NOT NULL,
        sample_size INTEGER NOT NULL,success_min INTEGER NOT NULL,starts INTEGER NOT NULL,expires INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'open',closed INTEGER,close_reason TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS business_observations(
        id INTEGER PRIMARY KEY,trial INTEGER NOT NULL REFERENCES business_trials(id),
        participant_hash TEXT NOT NULL,evidence_hash TEXT NOT NULL UNIQUE,
        outcome TEXT NOT NULL,observed_at INTEGER NOT NULL,recorded_at INTEGER NOT NULL,
        UNIQUE(trial,participant_hash));
        CREATE TABLE IF NOT EXISTS business_receipts(
        id INTEGER PRIMARY KEY,offer INTEGER NOT NULL REFERENCES commercial_offers(id),
        reference_hash TEXT NOT NULL UNIQUE,mode TEXT NOT NULL,kind TEXT NOT NULL,
        parent INTEGER REFERENCES business_receipts(id),amount_cents INTEGER NOT NULL,
        occurred_at INTEGER NOT NULL,recorded_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS business_events(
        id INTEGER PRIMARY KEY,at INTEGER NOT NULL,event TEXT NOT NULL,object_id INTEGER NOT NULL,
        detail TEXT NOT NULL);""")
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def log(c,event,oid,detail,t):
    c.execute('INSERT INTO business_events(at,event,object_id,detail) VALUES(?,?,?,?)',(t,event,oid,canonical(detail)))
def fields(b,keys):
    if not isinstance(b,dict) or set(b)!=set(keys)|{'confirm'} or b.get('confirm') is not True:
        raise ValueError('Confirmation explicite et champs exacts requis')
def integer(v,lo=1,hi=9007199254740991):
    if type(v) is not int or not lo<=v<=hi:raise ValueError('Entier hors limites')
    return v
def opaque(v):
    if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',v):raise ValueError('Référence opaque de 16–80 caractères (lettres, chiffres, tiret, underscore); jamais nom, email, clé ou numéro de carte')
    # Store only digests, not the original reference. Pseudonymization is not anonymization.
    return hashlib.sha256(v.encode()).hexdigest()
def offer_row(c,oid):
    row=c.execute("""SELECT o.* FROM commercial_offers o JOIN missions m ON m.id=o.mission
        WHERE o.id=? AND m.mode='cloud' AND m.state='terminée'""",(integer(oid),)).fetchone()
    if not row:raise ValueError('Offre interne achevée requise')
    return row
def gate(c,row):
    v=commercial.offer_status(c,row);p=portfolio.project(c,row['project'])
    latest=commercial.project_status(c,row['project'])['offer']
    reasons=list(v['gaps'])
    if not p or p['state']!='active':reasons.append('activité inactive')
    if not latest or latest['id']!=row['id']:reasons.append('offre remplacée')
    # Documentary/review gaps may justify an observation-only protocol, never a sale.
    permitted_gaps={'indices_documentaires_insuffisants','revue_independante_manquante_ou_reserves'}
    review=(v['review'] or {}).get('verdict')
    eligible=bool(p and p['state']=='active' and latest and latest['id']==row['id'] and row['artifact'] and
                  set(v['gaps'])<=permitted_gaps and review in ('study_further','propose_future_test'))
    return v,eligible,reasons
def frozen(v):
    return {k:v[k] for k in ('id','project','mission','artifact','artifact_sha256','plan','economics','review','gaps','state')}
def trial_row(c,tid):
    row=c.execute('SELECT * FROM business_trials WHERE id=?',(integer(tid),)).fetchone()
    if not row:raise ValueError('Protocole absent')
    return row
def trial_state(c,row,t):
    if row['state']!='open':return row['state']
    if t<row['starts']:return 'clock_error'
    if t>=row['expires']:return 'expired'
    if c.execute('SELECT COUNT(*) FROM business_observations WHERE trial=?',(row['id'],)).fetchone()[0]>=row['sample_size']:return 'sample_complete'
    try:
        v,eligible,_=gate(c,offer_row(c,row['offer']))
        if not eligible or digest(frozen(v))!=row['snapshot_sha256']:return 'reference_changed'
    except (ValueError,KeyError,TypeError,AttributeError):return 'reference_changed'
    return 'open'
def authorize(c,b,t=None):
    t=now() if t is None else t
    fields(b,('offer','metric','sample_size','success_min','duration_days','snapshot_sha256'))
    row=offer_row(c,b['offer']);v,eligible,_=gate(c,row)
    if not eligible:raise ValueError('Prérequis techniques, économiques ou revue insuffisants; aucune observation autorisée')
    if b['snapshot_sha256']!=digest(frozen(v)):raise ValueError('Offre ou prérequis modifiés; actualiser')
    if c.execute('SELECT 1 FROM business_trials WHERE offer=?',(row['id'],)).fetchone():raise ValueError('Un seul protocole par offre exacte; historique conservé')
    metric=b['metric'];plan=v['plan']
    if metric not in ('qualified_interest','consented_demo_request'):raise ValueError('Observation non transactionnelle uniquement; commandes payantes interdites')
    if plan['metric']!='paid_order_future' and metric!=plan['metric']:raise ValueError('Conserver la métrique non transactionnelle prévue')
    n=integer(b['sample_size'],1,plan['sample_size']);k=integer(b['success_min'],1,n);days=integer(b['duration_days'],1,plan['duration_days'])
    # No easier threshold than the historical protocol when the metric is unchanged.
    if metric==plan['metric'] and k*plan['sample_size']<plan['success_min']*n:
        raise ValueError('Seuil proportionnel inférieur au protocole initial')
    snap=frozen(v)
    tid=c.execute("""INSERT INTO business_trials(offer,project,artifact,snapshot,snapshot_sha256,metric,sample_size,success_min,starts,expires)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(row['id'],row['project'],row['artifact'],canonical(snap),digest(snap),metric,n,k,t,t+days*86400)).lastrowid
    log(c,'trial_authorized',tid,{'offer':row['id'],'metric':metric,'scope':'observation_only','external_spend_cents':0},t)
    return tid
def observe(c,b,t=None):
    t=now() if t is None else t
    fields(b,('trial','participant_ref','evidence_ref','outcome','observed_at','consent_attested'))
    row=trial_row(c,b['trial'])
    if trial_state(c,row,t)!='open':raise ValueError('Protocole clos, expiré, complet ou référence modifiée')
    if b['consent_attested'] is not True:raise ValueError('Participation volontaire et consentement attestés requis')
    participant=opaque(b['participant_ref']);evidence=opaque(b['evidence_ref'])
    if participant==evidence:raise ValueError('Références participant et preuve distinctes requises')
    allowed={'qualified_interest':('interest','no_interest'),'consented_demo_request':('demo_request','no_interest')}[row['metric']]
    if b['outcome'] not in allowed:raise ValueError('Observation incompatible avec la métrique')
    observed=integer(b['observed_at'],row['starts'],min(row['expires']-1,t))
    if c.execute('SELECT 1 FROM business_observations WHERE evidence_hash=? OR (trial=? AND participant_hash=?)',(evidence,row['id'],participant)).fetchone():
        raise ValueError('Participant ou preuve déjà compté')
    oid=c.execute("""INSERT INTO business_observations(trial,participant_hash,evidence_hash,outcome,observed_at,recorded_at)
        VALUES(?,?,?,?,?,?)""",(row['id'],participant,evidence,b['outcome'],observed,t)).lastrowid
    log(c,'observation_attested',oid,{'trial':row['id'],'source':'owner_attested','consent_attested':True},t)
    return oid
def close(c,b,t=None):
    t=now() if t is None else t
    fields(b,('trial',))
    row=trial_row(c,b['trial'])
    if row['state']!='open':raise ValueError('Protocole déjà clos')
    state=trial_state(c,row,t)
    reason=state if state!='open' else 'owner_revoked'
    c.execute("UPDATE business_trials SET state='closed',closed=?,close_reason=? WHERE id=?",(t,reason,row['id']))
    log(c,'trial_closed',row['id'],{'reason':reason},t)
    return row['id']
def receipt(c,b,t=None):
    """Manual historical accounting only; never makes a charge or establishes verified revenue."""
    t=now() if t is None else t
    fields(b,('offer','reference','mode','kind','parent','amount_cents','occurred_at','source_attested'))
    row=offer_row(c,b['offer'])
    if b['source_attested'] is not True:raise ValueError('Attester une transaction externe déjà survenue ou un test identifié')
    if b['mode'] not in ('test','owner_declared_live') or b['kind'] not in ('payment','refund'):
        raise ValueError('Mode test ou déclaration propriétaire uniquement')
    ref=opaque(b['reference']);amount=integer(b['amount_cents'],1,100000000)
    occurred=integer(b['occurred_at'],1,t)
    if c.execute('SELECT 1 FROM business_receipts WHERE reference_hash=?',(ref,)).fetchone():raise ValueError('Référence de transaction déjà enregistrée')
    parent=b['parent']
    if b['kind']=='payment':
        if parent is not None:raise ValueError('Paiement sans parent requis')
    else:
        original=c.execute("SELECT * FROM business_receipts WHERE id=? AND kind='payment'",(integer(parent),)).fetchone()
        if not original or original['offer']!=row['id'] or original['mode']!=b['mode'] or occurred<original['occurred_at']:
            raise ValueError('Remboursement : paiement d’origine exact, même mode et offre requis')
        refunded=c.execute("SELECT COALESCE(SUM(amount_cents),0) FROM business_receipts WHERE parent=? AND kind='refund'",(parent,)).fetchone()[0]
        if refunded+amount>original['amount_cents']:raise ValueError('Remboursement supérieur au paiement d’origine')
    rid=c.execute("""INSERT INTO business_receipts(offer,reference_hash,mode,kind,parent,amount_cents,occurred_at,recorded_at)
        VALUES(?,?,?,?,?,?,?,?)""",(row['id'],ref,b['mode'],b['kind'],parent,amount,occurred,t)).lastrowid
    log(c,'receipt_recorded',rid,{'source':'owner_attested','mode':b['mode'],'kind':b['kind'],'currency':'EUR','verified':False},t)
    return rid
def trial_status(c,row,t):
    items=[dict(x) for x in c.execute('SELECT * FROM business_observations WHERE trial=? ORDER BY id',(row['id'],))]
    positive=sum(x['outcome']!='no_interest' for x in items)
    state=trial_state(c,row,t)
    return {**dict(row),'snapshot':json.loads(row['snapshot']),'effective_state':state,'observations':len(items),'positive':positive,
        'sample_complete':len(items)==row['sample_size'],'threshold_reached':positive>=row['success_min'],
        'classification':'observations déclarées, non vérifiées; aucun verdict automatique de demande','items':items}
def status(c,t=None):
    t=now() if t is None else t
    catalog=[]
    for p in c.execute('SELECT * FROM projects ORDER BY id'):
        v=commercial.project_status(c,p['id'])['offer']
        if not v:continue
        row=offer_row(c,v['id']);v,eligible,reasons=gate(c,row)
        exists=c.execute('SELECT 1 FROM business_trials WHERE offer=?',(row['id'],)).fetchone()
        catalog.append({'offer':v['id'],'project':p['id'],'title':p['title'],'artifact':v['artifact'],
            'artifact_sha256':v['artifact_sha256'],'plan':v['plan'],'state':v['state'],'gaps':reasons,
            'review':v['review'],'economics':v['economics'],'snapshot_sha256':digest(frozen(v)),
            'observation_eligible':eligible and not bool(exists),'sale_authorized':False})
    trials=[trial_status(c,x,t) for x in c.execute('SELECT * FROM business_trials ORDER BY id DESC')]
    receipts=[dict(x) for x in c.execute('SELECT * FROM business_receipts ORDER BY id DESC')]
    totals=receipt_accounting.totals(receipts)
    return {'catalog':catalog,'trials':trials,'receipts':receipts,'totals':totals,'currency':'EUR',
        'verified_live_cents':0,'verified_live_available':False,'external_authorized':False,
        'external_spend_cents':0,'events':[dict(x) for x in c.execute('SELECT * FROM business_events ORDER BY id DESC')],
        'limit':LIMIT}
