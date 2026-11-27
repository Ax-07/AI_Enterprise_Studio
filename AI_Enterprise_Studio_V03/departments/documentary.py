"""Read-only documentary projections; no transport or semantic certification."""
import json

def excerpt_quality(text):
    # Conservative heuristic, not semantic verification.
    if len(text.strip())<120:return 'short_excerpt'
    if 'loading...' in text.lower():return 'possible_dynamic_shell'
    return 'text_available'

def mission(c,mid,full=False,*,quality):
    searches=[]
    for r in c.execute('SELECT id,query,status,result FROM searches WHERE mission=? ORDER BY id',(mid,)):
        item={k:r[k] for k in ('id','query','status')}
        try:results=json.loads(r['result'])
        except (ValueError,TypeError):results=[]
        if not isinstance(results,list):results=[]
        item['result_count']=len(results)
        if full:item['unverified_results']=results[:5]
        searches.append(item)
    pages=[]
    for r in c.execute('SELECT id,url,state,content,created FROM fetched WHERE mission=? ORDER BY id',(mid,)):
        item={k:r[k] for k in ('id','url','state','created')}
        try:d=json.loads(r['content'])
        except (ValueError,TypeError):d={}
        if not isinstance(d,dict):d={}
        if r['state']=='reçue':
            import hashlib
            excerpt=d.get('texte','')
            if isinstance(excerpt,str):
                item.update(chars=len(excerpt),excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),partial=bool(d.get('partiel')),quality=quality(excerpt))
                if full:item['excerpt']=excerpt
        elif r['state']=='échec':item['failure']=d.get('failure') or {'code':'historical_unknown','message':'Ancien échec; détail éventuel dans le journal.'}
        pages.append(item)
    return {'searches':searches,'pages':pages,'searches_received':sum(x['status']=='reçue' for x in searches),
        'pages_received':sum(x['state']=='reçue' for x in pages),'limit':'Extraits Brave non vérifiés; une page lue ne prouve pas la demande.'}

def exact_candidates(c,mid,*,quality):
    """Local, exact substrings, no semantic classification or new network calls."""
    import re,hashlib
    out=[]
    patterns=(r'[$€£]\s*\d',r'\b(?:USD|EUR|GBP|pricing|per month|par mois)\b',
              r'\b(?:error|errors|erreur|errors|manual|manually|time.sav|saves? time|hours|problème|difficult|reviews?|avis)\b')
    for row in c.execute("SELECT id,url,content FROM fetched WHERE mission=? AND state='reçue' ORDER BY id DESC LIMIT 3",(mid,)):
        try:d=json.loads(row['content']);raw=d['texte']
        except (ValueError,KeyError,TypeError):continue
        if not isinstance(raw,str) or quality(raw)!='text_available':continue
        candidates=[]
        for pattern in patterns:
            for match in re.finditer(pattern,raw,re.I):
                start=max(0,match.start()-65);end=min(len(raw),match.end()+100)
                if any(abs(start-x['offset'])<80 for x in candidates):continue
                quote=raw[start:end]
                if len(quote)>=12:candidates.append({'offset':start,'quote':quote})
                if len(candidates)>=4:break
            if len(candidates)>=4:break
        if candidates:out.append({'page':row['id'],'url':row['url'],'sha256':hashlib.sha256(raw.encode()).hexdigest(),'candidates':candidates})
    return out
