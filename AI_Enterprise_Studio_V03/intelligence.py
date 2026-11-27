"""Official macro evidence and explicitly hypothetical economics. No commercial proof."""
import hashlib,http.client,json,math,re,ssl
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlencode
from departments import macroeconomic
from departments import provenance

CAP='worldbank.market'
COUNTRIES=tuple('AUS AUT BEL BRA CAN CHE CHL CHN COL CZE DEU DNK ESP FIN FRA GBR GRC HUN IDN IND IRL ISR ITA JPN KEN KOR MAR MEX MYS NLD NOR NZL PHL POL PRT ROU SAU SGP SWE THA TUN TUR USA VNM ZAF'.split())
INDICATORS={'SP.POP.TOTL':('Population','personnes'), 'IT.NET.USER.ZS':('Utilisateurs internet','% population'), 'NY.GDP.PCAP.CD':('PIB par habitant','USD courants')}
LIMIT='Indicateurs macroéconomiques officiels; couverture et PIB ne mesurent ni demande sectorielle, ni concurrence, ni volonté de payer.'
MAX_BYTES=65536

def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('Clé JSON dupliquée')
            d[k]=v
        return d
    def constant(v):raise ValueError('Nombre non fini')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)

def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(d):return hashlib.sha256(canonical(d).encode()).hexdigest()

def init(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS market_sources(
        run INTEGER PRIMARY KEY REFERENCES connector_runs(id), source TEXT NOT NULL, url TEXT NOT NULL,
        retrieved TEXT NOT NULL, raw_sha256 TEXT NOT NULL, snapshot TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS market_source_raw(run INTEGER PRIMARY KEY REFERENCES market_sources(run), raw_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS market_assessments(
        id INTEGER PRIMARY KEY, opportunity INTEGER NOT NULL REFERENCES opportunities(id), mission INTEGER NOT NULL REFERENCES missions(id),
        agent TEXT NOT NULL, opportunity_sha256 TEXT NOT NULL, assumptions TEXT NOT NULL, source_runs TEXT NOT NULL,
        result TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS market_assessments_opp ON market_assessments(opportunity,id);""")

def request_spec(text):
    if not isinstance(text,str) or len(text)>500:raise ValueError('Requête marché invalide')
    try:d=decode(text)
    except (ValueError,TypeError,RecursionError):raise ValueError('JSON marché invalide') from None
    if not isinstance(d,dict) or set(d)!={'countries','year'}:raise ValueError('Format: {"countries":["FRA","GBR"],"year":2023}')
    cs=d['countries'];year=d['year']
    if not isinstance(cs,list) or not 2<=len(cs)<=3 or any(not isinstance(v,str) or v not in COUNTRIES for v in cs) or len(set(cs))!=len(cs):
        raise ValueError('Deux ou trois pays ISO3 distincts autorisés')
    if type(year) is not int or not 2015<=year<datetime.now(timezone.utc).year:raise ValueError('Année 2015 à dernière année civile complète')
    return canonical({'countries':sorted(cs),'year':year})

def url_for(d):
    return 'https://api.worldbank.org/v2/country/'+';'.join(d['countries'])+'/indicator/'+';'.join(INDICATORS)+'?'+urlencode({'source':2,'date':d['year'],'format':'json','per_page':50})

def parse(raw,d):
    return macroeconomic.parse(raw,d,decode=decode,MAX_BYTES=MAX_BYTES,INDICATORS=INDICATORS,LIMIT=LIMIT)

def fetch(value):
    d=decode(request_spec(value));url=url_for(d)
    conn=http.client.HTTPSConnection('api.worldbank.org',443,timeout=12,context=ssl.create_default_context())
    try:
        conn.request('GET',url.split('api.worldbank.org',1)[1],headers={'Accept':'application/json','User-Agent':'AI-Enterprise-Studio/0.5.0','Connection':'close'})
        response=conn.getresponse()
        if response.status!=200:raise RuntimeError('HTTP '+str(response.status))
        raw=response.read(MAX_BYTES+1)
        snapshot=parse(raw,d)
        return {'source':'World Bank / WDI (source 2)','url':url,'retrieved':datetime.now(timezone.utc).isoformat(timespec='seconds'),'raw_sha256':hashlib.sha256(raw).hexdigest(),'snapshot':snapshot,'snapshot_sha256':digest(snapshot),'raw_json':raw.decode('utf8')}
    finally:conn.close()

def record(c,rid,result):
    return provenance.record(c,rid,result,digest=digest,url_for=url_for,parse=parse,canonical=canonical)

def raw_integrity(c,r,d):
    return provenance.raw_integrity(c,r,d,parse=parse,url_for=url_for)

def source(c,rid,mid):
    return provenance.source(c,rid,mid,CAP=CAP,decode=decode,digest=digest,raw_integrity=raw_integrity)

def sources(c,mid):
    return provenance.sources(c,mid,source=source)

def compare_ref(text):
    if not isinstance(text,str) or len(text)>200:raise ValueError('Référence trop longue')
    try:d=decode(text)
    except (ValueError,TypeError,RecursionError):raise ValueError('JSON de référence requis') from None
    if not isinstance(d,dict) or set(d)!={'source_run'} or type(d['source_run']) is not int or not 1<=d['source_run']<=9007199254740991:raise ValueError('Format {"source_run": ID du relevé Banque mondiale de cette mission}')
    return canonical(d)

def comparable(d):
    return len(compare_rows(d))>=2

def compare_rows(d):
    return macroeconomic.compare_rows(d,Decimal=Decimal,ROUND_HALF_UP=ROUND_HALF_UP)

def compare_input(c,value,mid):
    rid=decode(compare_ref(value))['source_run'];d=source(c,rid,mid)
    rows=compare_rows(d)
    if len(rows)<2:raise ValueError('Deux pays avec population et couverture internet de la même année requis')
    return canonical({'rows':rows})

def page_reference(c,mid,rid):
    return provenance.page_reference(c,mid,rid,decode=decode)

def page_refs(c,mid):
    return provenance.page_refs(c,mid,page_reference=page_reference)

def opportunity_hash(o):
    return digest({k:o[k] for k in ('title','body','next_test')})

def assess(c,mid,agent,target,text):
    if agent!='MIDAS' or not target.isdigit() or len(target)>12:raise ValueError('Évaluation MIDAS, ID opportunité requis')
    o=c.execute('SELECT * FROM opportunities WHERE id=? AND mission=?',(int(target),mid)).fetchone()
    if not o:raise ValueError('Opportunité de cette mission requise')
    if c.execute('SELECT COUNT(*) FROM market_assessments WHERE mission=?',(mid,)).fetchone()[0]>=6:raise ValueError('Plafond de six évaluations par mission')
    try:d=decode(text)
    except (ValueError,TypeError,RecursionError):raise ValueError('JSON économique invalide') from None
    fields={'price_cents','variable_cost_cents','fixed_month_cents','monthly_units','automation_pct','risk','source_runs','rationale'}
    if not isinstance(d,dict) or not fields<=set(d) or set(d)-fields-{'page_refs'}:raise ValueError('Champs d’évaluation incomplets')
    for k,lo,hi in [('price_cents',1,10000000),('variable_cost_cents',0,10000000),('fixed_month_cents',0,100000000),('monthly_units',1,100000),('automation_pct',0,100),('risk',1,5)]:
        if type(d[k]) is not int or not lo<=d[k]<=hi:raise ValueError('Hypothèse hors limite : '+k)
    if not isinstance(d['rationale'],str) or not 20<=len(d['rationale'])<=1200:raise ValueError('Justification de 20 à 1200 caractères')
    ids=d['source_runs']
    if not isinstance(ids,list) or len(ids)>3 or any(type(i) is not int or not 1<=i<=9007199254740991 for i in ids) or len(set(ids))!=len(ids):raise ValueError('Références de source invalides')
    for rid in ids:source(c,rid,mid)
    pages=d.get('page_refs',[])
    if not isinstance(pages,list) or len(pages)>5 or any(type(x) is not int or not 1<=x<=9007199254740991 for x in pages) or len(set(pages))!=len(pages):raise ValueError('Références de pages invalides')
    page_evidence=[page_reference(c,mid,p) for p in pages]
    price=d['price_cents'];contribution=price-d['variable_cost_cents'];fixed=d['fixed_month_cents'];units=d['monthly_units']
    margin_bp=contribution*10000//price
    breakeven=(fixed+contribution-1)//contribution if contribution>0 else None
    monthly=contribution*units-fixed
    # Score 0–100, deliberately not a demand probability. Macro evidence is separate.
    components={'margin':max(0,min(40,margin_bp*40//10000)),
                'scenario':max(0,min(20,monthly*20//(price*units))),
                'automation':d['automation_pct']*25//100,'risk':(5-d['risk'])*15//4}
    result={'score':sum(components.values()) if contribution>0 and monthly>0 else 0,'components':components,'contribution_cents':contribution,'margin_bp':margin_bp,'breakeven_units':breakeven,'monthly_result_cents':monthly,'scenario_viable':contribution>0 and monthly>0,'evidence_count':len(ids),'page_count':len(pages),'pages':page_evidence,'classification':'hypothèse non validée','limit':'EUR hors TVA; hypothèses agent non certifiées. Coût variable doit inclure acquisition, frais, retours, cotisations, assistance; fixe inclut exploitation. Résultat avant impôt et rémunération propriétaire si non inclus. Aucune preuve de ventes.'}
    rid=c.execute('INSERT INTO market_assessments(opportunity,mission,agent,opportunity_sha256,assumptions,source_runs,result) VALUES(?,?,?,?,?,?,?)',(o['id'],mid,agent,opportunity_hash(o),canonical(d),canonical(ids),canonical(result))).lastrowid
    return {'assessment':rid,'opportunity':o['id'],**result}

def ranking(c):
    out=[]
    for r in c.execute("""SELECT a.*,o.title,o.body,o.next_test,p.id AS project FROM market_assessments a
        JOIN opportunities o ON o.id=a.opportunity JOIN missions m ON m.id=a.mission
        LEFT JOIN projects p ON p.opportunity=o.id
        WHERE m.mode='cloud' AND m.state='terminée' AND (p.id IS NULL OR p.state='active')
        AND a.id=(SELECT MAX(b.id) FROM market_assessments b WHERE b.opportunity=a.opportunity)
        ORDER BY a.id DESC"""):
        if opportunity_hash(r)!=r['opportunity_sha256']:continue
        try:
            for rid in decode(r['source_runs']):source(c,rid,r['mission'])
            res=decode(r['result'])
            if any(page_reference(c,r['mission'],p['id'])!=p for p in res.get('pages',[])):continue
        except ValueError:continue
        out.append({'id':r['id'],'opportunity':r['opportunity'],'mission':r['mission'],'project':r['project'],'title':r['title'],'created':r['created'],'assumptions':decode(r['assumptions']),'result':decode(r['result'])})
    return sorted(out,key=lambda r:(-r['result']['score'],r['opportunity']))

def status(c,full=False):
    records=[]
    for r in c.execute("""SELECT s.*,r.actor,r.mission FROM market_sources s JOIN connector_runs r ON r.id=s.run WHERE r.state='received' ORDER BY s.run DESC LIMIT 30"""):
        d=decode(r['snapshot'])
        ok,raw=raw_integrity(c,r,d)
        records.append({**dict(r),'snapshot':d,'integrity':digest(d)==r['snapshot_sha256'] and ok,'raw_preserved':raw is not None,**({'raw_json':raw} if full else {})})
    comparisons=[]
    for r in c.execute("""SELECT r.id,r.mission,r.actor,w.execution_id,w.result FROM connector_runs r JOIN connector_workflow_results w ON w.run=r.id WHERE r.capability='n8n.market_compare' AND r.state='received' ORDER BY r.id DESC LIMIT 30"""):
        comparisons.append({**dict(r),'result':decode(r['result'])})
    return {'sources':records,'comparisons':comparisons,'ranking':ranking(c),'limit':LIMIT+' Classement sur hypothèses EUR, sans décision automatique de lancement.'}
