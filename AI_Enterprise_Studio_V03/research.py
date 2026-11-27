"""Bounded public-reading diagnostics. No AI, Brave, arbitrary target, or weakened TLS."""
import ssl,socket,json,sys
from datetime import datetime,timezone
from departments import documentary

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
    return documentary.excerpt_quality(text)

def mission(c,mid,full=False):
    return documentary.mission(c,mid,full,quality=excerpt_quality)

def exact_candidates(c,mid):
    return documentary.exact_candidates(c,mid,quality=excerpt_quality)
