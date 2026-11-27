"""Official macro evidence and explicitly hypothetical economics. No commercial proof."""
import hashlib,http.client,json,math,re,ssl
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlencode
from departments import macroeconomic
from departments import provenance
from departments import opportunity_assessment

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
    return opportunity_assessment.opportunity_hash(o,digest=digest)

def assess(c,mid,agent,target,text):
    return opportunity_assessment.assess(c,mid,agent,target,text,decode=decode,source=source,page_reference=page_reference,opportunity_hash=opportunity_hash,canonical=canonical)

def ranking(c):
    return opportunity_assessment.ranking(c,opportunity_hash=opportunity_hash,decode=decode,source=source,page_reference=page_reference)

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
