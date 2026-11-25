"""Bounded public-reading diagnostics. No AI, Brave, arbitrary target, or weakened TLS."""
import ssl,socket,json,sys
from datetime import datetime,timezone

PROBES=(
 ('reference','https://example.com/'),
 ('eurostat','https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction'),
 ('eurlex','https://eur-lex.europa.eu/EN/legal-content/summary/open-data-and-the-reuse-of-public-sector-information.html'),
)
LIMIT='Lectures HTTPS publiques uniquement; diagnostic ponctuel, sans appel OpenAI ou Brave. Ne pas contourner les certificats ni les protections des sites.'

def tls_context():
    # System trust is retained. If the locally installed certifi package exists,
    # add its public Mozilla roots; never download roots or disable verification.
    ctx=ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return ctx,'system'
    try:ctx.load_verify_locations(cafile=certifi.where())
    except (OSError,ssl.SSLError):return ctx,'system'
    return ctx,'system+certifi'

def failure(e):
    if isinstance(e,ssl.SSLCertVerificationError):
        return {'code':'tls_certificate','message':str(e)[:200],
            'advice':'Vérifier date/heure, mises à jour Windows/Python, chaîne serveur et magasin de confiance. Ne pas désactiver TLS.'}
    if isinstance(e,ssl.SSLError):code='tls_error'
    elif isinstance(e,(TimeoutError,socket.timeout)):code='timeout'
    elif isinstance(e,socket.gaierror):code='dns_error'
    elif str(e).startswith('HTTP '):code='http_'+str(e).split()[1]
    elif isinstance(e,ValueError):code='read_policy'
    else:code='network_error'
    return {'code':code,'message':str(e)[:200],
        'advice':'Essayer une autre URL publique déjà issue des résultats Brave; ne pas contourner une protection ni répéter cette URL.'}

def diagnostic(fetch):
    ctx,trust=tls_context()
    checks=[]
    for name,url in PROBES:
        try:
            data=fetch(url)
            checks.append({'name':name,'url':url,'state':'received','chars':len(data['texte']),'partial':bool(data.get('partiel'))})
        except Exception as e:checks.append({'name':name,'url':url,'state':'failed',**failure(e)})
    return {'date':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],
        'openssl':ssl.OPENSSL_VERSION,'trust':trust,'verify_required':ctx.verify_mode==ssl.CERT_REQUIRED,
        'hostname_check':ctx.check_hostname,'checks':checks,'limit':LIMIT}

def excerpt_quality(text):
    # Conservative heuristic, not semantic verification.
    if len(text.strip())<120:return 'short_excerpt'
    if 'loading...' in text.lower():return 'possible_dynamic_shell'
    return 'text_available'

def mission(c,mid,full=False):
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
                item.update(chars=len(excerpt),excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),partial=bool(d.get('partiel')),quality=excerpt_quality(excerpt))
                if full:item['excerpt']=excerpt
        elif r['state']=='échec':item['failure']=d.get('failure') or {'code':'historical_unknown','message':'Ancien échec; détail éventuel dans le journal.'}
        pages.append(item)
    return {'searches':searches,'pages':pages,'searches_received':sum(x['status']=='reçue' for x in searches),
        'pages_received':sum(x['state']=='reçue' for x in pages),'limit':'Extraits Brave non vérifiés; une page lue ne prouve pas la demande.'}
