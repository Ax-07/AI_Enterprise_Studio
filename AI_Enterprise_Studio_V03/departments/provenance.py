"""Source provenance and integrity; caller owns database and transaction.

No network transport or certification of commercial demand.
"""
import hashlib

def record(c,rid,result,*,digest,url_for,parse,canonical):
    snapshot=result['snapshot']
    raw=result['raw_json'].encode('utf8')
    if digest(snapshot)!=result['snapshot_sha256'] or hashlib.sha256(raw).hexdigest()!=result['raw_sha256']:raise ValueError('Empreinte de source incohérente')
    req={'countries':snapshot['countries'],'year':snapshot['year']}
    if result['url']!=url_for(req) or parse(raw,req)!=snapshot:raise ValueError('Projection de source incohérente')
    c.execute('INSERT INTO market_sources(run,source,url,retrieved,raw_sha256,snapshot,snapshot_sha256) VALUES(?,?,?,?,?,?,?)',(rid,result['source'],result['url'],result['retrieved'],result['raw_sha256'],canonical(snapshot),result['snapshot_sha256']))
    c.execute('INSERT INTO market_source_raw(run,raw_json) VALUES(?,?)',(rid,result['raw_json']))

def raw_integrity(c,r,d,*,parse,url_for):
    row=c.execute('SELECT raw_json FROM market_source_raw WHERE run=?',(r['run'],)).fetchone()
    if not row:return False,None
    raw=row['raw_json'].encode('utf8')
    try:ok=hashlib.sha256(raw).hexdigest()==r['raw_sha256'] and parse(raw,{'countries':d['countries'],'year':d['year']})==d and r['url']==url_for({'countries':d['countries'],'year':d['year']})
    except (ValueError,TypeError,KeyError,AttributeError):ok=False
    return ok,row['raw_json']

def source(c,rid,mid,*,CAP,decode,digest,raw_integrity):
    r=c.execute("""SELECT s.*,r.mission,r.state FROM market_sources s JOIN connector_runs r ON r.id=s.run
        WHERE s.run=? AND r.mission=? AND r.capability=? AND r.state='received'""",(rid,mid,CAP)).fetchone()
    if not r:raise ValueError('Source officielle reçue de cette mission requise')
    d=decode(r['snapshot'])
    if digest(d)!=r['snapshot_sha256'] or not raw_integrity(c,r,d)[0]:raise ValueError('Empreinte ou projection de source modifiée')
    return d

def sources(c,mid,*,source):
    out=[]
    for r in c.execute("""SELECT s.*,r.mission FROM market_sources s JOIN connector_runs r ON r.id=s.run WHERE r.mission=? AND r.state='received' ORDER BY s.run DESC LIMIT 3""",(mid,)):
        try:d=source(c,r['run'],mid)
        except ValueError:continue
        out.append({'run':r['run'],'url':r['url'],'retrieved':r['retrieved'],'snapshot':d})
    return out

def page_reference(c,mid,rid,*,decode):
    r=c.execute("SELECT id,url,content,created FROM fetched WHERE id=? AND mission=? AND state='reçue'",(rid,mid)).fetchone()
    if not r:raise ValueError('Page effectivement lue dans cette mission requise')
    d=decode(r['content'])
    if not isinstance(d,dict) or d.get('url')!=r['url'] or not isinstance(d.get('texte'),str):raise ValueError('Extrait de page invalide')
    return {'id':r['id'],'url':r['url'],'date':d.get('date') or r['created'],'partial':bool(d.get('partiel')),'excerpt_sha256':hashlib.sha256(d['texte'].encode()).hexdigest(),'limit':'Page publique lue, extrait non certifié; pas une validation de demande.'}

def page_refs(c,mid,*,page_reference):
    out=[]
    for r in c.execute("SELECT id FROM fetched WHERE mission=? AND state='reçue' ORDER BY id DESC LIMIT 8",(mid,)):
        try:out.append(page_reference(c,mid,r['id']))
        except ValueError:continue
    return out

