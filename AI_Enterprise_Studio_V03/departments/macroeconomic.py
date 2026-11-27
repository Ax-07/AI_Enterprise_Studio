"""Pure macroeconomic projections; no database, transport or commercial claims."""
import math,re

def parse(raw,d,*,decode,MAX_BYTES,INDICATORS,LIMIT):
    if len(raw)>MAX_BYTES:raise ValueError('Réponse Banque mondiale trop volumineuse')
    result=decode(raw)
    if not isinstance(result,list) or len(result)!=2 or not isinstance(result[0],dict) or not isinstance(result[1],list):raise ValueError('Contrat Banque mondiale invalide')
    meta,rows=result
    try:
        if int(meta['page'])!=1 or int(meta['pages'])!=1 or int(meta['total'])!=len(rows):raise ValueError()
    except (ValueError,TypeError,KeyError):raise ValueError('Pagination Banque mondiale non confirmée') from None
    update=meta.get('lastupdated')
    if not isinstance(update,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',update):update=None
    seen={}
    for r in rows:
        if not isinstance(r,dict) or not isinstance(r.get('indicator'),dict):raise ValueError('Observation invalide')
        country=r.get('countryiso3code');indicator=r['indicator'].get('id');year=r.get('date')
        if country not in d['countries'] or indicator not in INDICATORS or year!=str(d['year']) or (country,indicator) in seen:raise ValueError('Pays, indicateur, année ou doublon inattendu')
        v=r.get('value')
        if v is not None:
            if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('Valeur statistique invalide')
            if indicator=='SP.POP.TOTL' and (v>2000000000 or int(v)!=v):raise ValueError('Population invalide')
            if indicator=='IT.NET.USER.ZS' and v>100:raise ValueError('Pourcentage invalide')
            if indicator=='NY.GDP.PCAP.CD' and v>2000000:raise ValueError('PIB par habitant invalide')
        seen[country,indicator]=v
    observations=[{'country':country,'year':d['year'],'indicator':i,'value':seen.get((country,i)),'unit':INDICATORS[i][1]} for country in d['countries'] for i in INDICATORS]
    if not any(o['value'] is not None for o in observations):raise ValueError('Aucune observation disponible')
    return {'countries':d['countries'],'year':d['year'],'last_updated':update,'observations':observations,'limit':LIMIT}

def compare_rows(d,*,Decimal,ROUND_HALF_UP):
    v={(r['country'],r['indicator']):r['value'] for r in d['observations']}
    rows=[]
    for country in d['countries']:
        pop=v[country,'SP.POP.TOTL'];pct=v[country,'IT.NET.USER.ZS']
        if pop is not None and pct is not None:
            rows.append({'country':country,'population':int(pop),'internet_bp':int((Decimal(str(pct))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))})
    return rows

