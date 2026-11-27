"""Trusted, bounded experimental profiles. Never execute product code on the host."""
import collections,hashlib,json,math,random,re
import verification
from departments import laboratory_benchmarks

IMAGE='aes-lab:0.3.8'
PROFILE='catalogue-v1'
VERSION=1
LIMIT='Données synthétiques seulement. Temps de clic et lecture navigateur, pas temps CPU, relecture humaine, sécurité ou demande commerciale.'
SIZES=(100,300,1000)
DEFAULT_SEED=42

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS laboratory_runs(
        id INTEGER PRIMARY KEY, artifact INTEGER NOT NULL REFERENCES artifacts(id),
        campaign INTEGER REFERENCES campaigns(id), profile TEXT NOT NULL, revision INTEGER NOT NULL,
        size INTEGER NOT NULL, seed INTEGER NOT NULL, sha256 TEXT NOT NULL,
        status TEXT NOT NULL, result TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS lab_artifact ON laboratory_runs(artifact,id);
        CREATE UNIQUE INDEX IF NOT EXISTS lab_once_campaign ON laboratory_runs(campaign) WHERE campaign IS NOT NULL;""")

def digest(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def encode(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))

def catalogue(size,seed):
    return laboratory_benchmarks.catalogue(size,seed,sizes=SIZES,random=random,encode=encode)

PROFILES={PROFILE:{'revision':VERSION,'generate':catalogue,'auto_names':('audit_catalogue.html',),'label':'Audit catalogue JSON — SKU, locale, titre'}}
def supports(row):
    return bool(row and row['name'].lower() in PROFILES[PROFILE]['auto_names'])

def score(fixtures,observed):
    return laboratory_benchmarks.score(fixtures,observed,collections=collections,math=math)

def evaluate(row,profile,size,seed,enabled):
    if not isinstance(profile,str) or profile not in PROFILES:raise ValueError('Profil laboratoire inconnu')
    if not row['name'].lower().endswith('.html'):raise ValueError('Ce profil exige un produit HTML, pas un fichier de cas JSON')
    fixtures=PROFILES[profile]['generate'](size,seed)
    base={'profile':profile,'revision':PROFILES[profile]['revision'],'size':size,'seed':seed,'sha256':digest(row['content']),
          'fixture_sha256':digest(encode(fixtures)),'fixtures':fixtures,'limit':LIMIT,'provenance':'LABORATOIRE_LOCAL'}
    if not enabled:return {**base,'status':'unavailable','error':'Bac à sable HTML désactivé','metrics':None,'cases':[]}
    if len(row['content'].encode('utf8'))>verification.MAX_BYTES:return {**base,'status':'unavailable','error':'Produit HTML trop volumineux','metrics':None,'cases':[]}
    try:
        # The browser receives inputs, not expected outputs. Only the trusted host computes scores.
        cases=[{'name':f['name'],'input':f['input']} for f in fixtures]
        observed=verification.browser_results(row['content'],cases,image=IMAGE,mode='laboratory')
        return {**base,**score(fixtures,observed)}
    except RuntimeError as e:return {**base,'status':'unavailable','error':str(e)[:250],'metrics':None,'cases':[]}

def run(s,aid,profile,size,seed,cfg,campaign=None):
    if type(aid) is not int or not 1<=aid<=9007199254740991:raise ValueError('Fichier invalide')
    with s.db() as c:
        row=c.execute("""SELECT a.* FROM artifacts a JOIN missions m ON m.id=a.mission
            WHERE a.id=? AND m.mode='cloud' AND m.state='terminée' AND a.agent='NEXUS'""",(aid,)).fetchone()
        if not row:raise ValueError('Produit NEXUS Cloud terminé requis')
        row=dict(row)
        if campaign is not None:
            owner=c.execute("""SELECT 1 FROM campaigns c JOIN campaign_projects cp ON cp.campaign=c.id
                JOIN project_missions pm ON pm.project=cp.project
                WHERE c.id=? AND c.state='actif' AND pm.mission=? AND json_extract(c.permissions,'$.tests')=1""",(campaign,row['mission'])).fetchone()
            if not owner or c.execute('SELECT 1 FROM laboratory_runs WHERE campaign=?',(campaign,)).fetchone():
                raise ValueError('Expérience non autorisée ou déjà exécutée dans cette campagne')
    result=evaluate(row,profile,size,seed,cfg.get('html_sandbox_enabled',False))
    with s.db() as c:
        rid=c.execute("""INSERT INTO laboratory_runs(artifact,campaign,profile,revision,size,seed,sha256,status,result)
            VALUES(?,?,?,?,?,?,?,?,?)""",(aid,campaign,profile,result['revision'],size,seed,result['sha256'],result['status'],encode(result))).lastrowid
    return {'id':rid,'artifact':aid,**result}

def summary_row(row):
    result=json.loads(row['result'])
    return {**{k:row[k] for k in ('id','artifact','campaign','profile','revision','size','seed','sha256','status','created')},
            'metrics':result.get('metrics'),'error':result.get('error'),'times':[{ 'name':x['name'],'elapsed_ms':x['elapsed_ms']} for x in result.get('cases',[]) if 'elapsed_ms' in x]}

def canonical(c,row):
    if not supports(row):return None
    r=c.execute("""SELECT * FROM laboratory_runs WHERE artifact=? AND sha256=? AND profile=? AND revision=?
        AND size=300 AND seed=? ORDER BY id DESC LIMIT 1""",(row['id'],digest(row['content']),PROFILE,VERSION,DEFAULT_SEED)).fetchone()
    return summary_row(r) if r else None

def status(c):
    return {'profile':PROFILE,'sizes':SIZES,'default_seed':DEFAULT_SEED,'limit':LIMIT,
            'runs':[summary_row(r) for r in c.execute('SELECT * FROM laboratory_runs ORDER BY id DESC LIMIT 100')],
            'products':[dict(r) for r in c.execute("""SELECT a.id,a.name,a.version,a.mission FROM artifacts a JOIN missions m ON m.id=a.mission
                WHERE m.mode='cloud' AND m.state='terminée' AND a.agent='NEXUS' AND lower(a.name) LIKE '%.html' ORDER BY a.id DESC""")]}
