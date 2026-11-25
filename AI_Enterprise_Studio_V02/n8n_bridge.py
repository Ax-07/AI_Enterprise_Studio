"""Fixed local n8n contracts. No admin API, dynamic URLs, secrets in payloads or arbitrary code."""
import http.client,json,os,re,secrets

HEALTH='n8n.health'
METRICS='n8n.metrics'
PROTOCOL='aes-n8n-v1'
PATHS={HEALTH:'/webhook/aes-v1-health',METRICS:'/webhook/aes-v1-metrics'}
MAX_BYTES=8192
ROLES=('ATLAS','ORION','MIDAS','HERMES','SENTINEL','NEXUS','PROMETHEUS')
class Unconfirmed(RuntimeError):pass

def configured():
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{32,128}',os.environ.get('AES_N8N_TOKEN','')))

def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('Clé JSON dupliquée')
            d[k]=v
        return d
    def constant(v):raise ValueError('Nombre JSON invalide')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)

def validate(cap,text):
    if not isinstance(text,str) or len(text)>4096:raise ValueError('Paramètre n8n invalide')
    try:d=decode(text)
    except (ValueError,RecursionError,TypeError):raise ValueError('Objet JSON n8n invalide') from None
    if cap==HEALTH and type(d) is dict and not d:return '{}'
    if cap==METRICS and type(d) is dict and set(d)=={'values'}:
        a=d['values']
        if isinstance(a,list) and 1<=len(a)<=100 and all(type(v) is int and -100000000<=v<=100000000 for v in a):
            return json.dumps(d,separators=(',',':'))
    raise ValueError('Contrat n8n : {} pour health; {"values":[1,2,3]} pour metrics (1 à 100 entiers bornés)')

def expected(cap,value):
    if cap==HEALTH:return {'ready':True}
    a=json.loads(value)['values']
    return {'count':len(a),'sum':sum(a),'min':min(a),'max':max(a)}

def call(cap,value,request_id):
    token=os.environ.get('AES_N8N_TOKEN','')
    if not configured():raise ValueError('Authentification n8n locale non configurée')
    value=validate(cap,value)
    if not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('Identifiant de requête invalide')
    body=json.dumps({'protocol':PROTOCOL,'request_id':request_id,'input':json.loads(value)},separators=(',',':')).encode()
    conn=http.client.HTTPConnection('127.0.0.1',5678,timeout=12)
    try:
        conn.request('POST',PATHS[cap],body=body,headers={'Content-Type':'application/json','Accept':'application/json','X-AES-Token':token,'Connection':'close'})
        resp=conn.getresponse()
        if resp.status!=200:raise Unconfirmed('HTTP '+str(resp.status))
        raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise Unconfirmed('Réponse trop volumineuse')
        try:d=decode(raw)
        except (ValueError,RecursionError,UnicodeError):raise Unconfirmed('Contrat de réponse invalide') from None
        if not isinstance(d,dict) or set(d)!={'protocol','request_id','execution_id','result'} or d['protocol']!=PROTOCOL or d['request_id']!=request_id or not isinstance(d['execution_id'],str) or not re.fullmatch(r'[0-9]{1,20}',d['execution_id']):
            raise Unconfirmed('Contrat de réponse invalide')
        exp=expected(cap,value)
        r=d['result']
        if not isinstance(r,dict) or set(r)!=set(exp) or any(type(r[k]) is not type(v) or r[k]!=v for k,v in exp.items()):
            raise Unconfirmed('Résultat incohérent')
        # Return trusted projection, never headers, raw response or credentials.
        return {'request_id':request_id,'execution_id':d['execution_id'],'result':exp,'protocol':PROTOCOL}
    except (OSError,http.client.HTTPException) as e:
        raise Unconfirmed(type(e).__name__) from None
    finally:conn.close()
