"""Bounded read-only evidence; never a certification or a new test."""
import hashlib
import verification
import laboratory

STATUSES=frozenset(('passed','failed','invalid','unavailable'))
DETAIL_LIMIT=256*1024

def decode(raw):
    try:
        d=verification.decode(raw)
        return d if isinstance(d,dict) else {}
    except (ValueError,TypeError,RecursionError,OverflowError):
        return {}

def identity(content,sha):
    if not isinstance(content,str) or not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):return 'unavailable'
    return 'match' if hashlib.sha256(content.encode('utf8')).hexdigest()==sha else 'changed'

def checks_of(data):
    raw=data.get('checks')
    if not isinstance(raw,list) or len(raw)>20:return None
    if any(not isinstance(x,dict) or type(x.get('passed')) is not bool for x in raw):return None
    return [{'name':x['name'][:100] if isinstance(x.get('name'),str) else 'Assertion sans nom','passed':x['passed']} for x in raw]

def status_of(data):
    value=data.get('status')
    return value if isinstance(value,str) and value in STATUSES else 'unreadable'

def read(db):
    result=[]
    for row in db.execute("""SELECT v.id,v.artifact,v.mission,v.agent,v.created,
        a.name,a.version,a.mission AS source_mission,m.mode,vm.mode AS test_mode,
        CASE WHEN length(CAST(a.content AS BLOB))<=? THEN a.content END AS content,
        CASE WHEN length(CAST(v.result AS BLOB))<=? THEN v.result END AS payload
        FROM verification_results v JOIN artifacts a ON a.id=v.artifact
        JOIN missions m ON m.id=a.mission JOIN missions vm ON vm.id=v.mission
        ORDER BY v.id DESC LIMIT 50""",(verification.MAX_BYTES,DETAIL_LIMIT)):
        data=decode(row['payload']);status=status_of(data);checks=checks_of(data)
        if checks is None or (status=='passed' and (not checks or not all(c['passed'] for c in checks))) or (status=='failed' and (not checks or all(c['passed'] for c in checks))):status='unreadable'
        result.append({'kind':'verification',**{k:row[k] for k in ('id','artifact','mission','agent','created','name','version','source_mission','mode','test_mode')},
            'status':status,'identity':identity(row['content'],data.get('sha256')),'checks':checks or [],'limit':verification.LIMIT})
    for row in db.execute("""SELECT l.id,l.artifact,l.created,l.profile,l.revision,l.size,l.sha256,l.status,
        a.name,a.version,a.mission AS source_mission,m.mode,
        CASE WHEN length(CAST(a.content AS BLOB))<=? THEN a.content END AS content,
        CASE WHEN length(CAST(l.result AS BLOB))<=? THEN l.result END AS payload
        FROM laboratory_runs l JOIN artifacts a ON a.id=l.artifact
        JOIN missions m ON m.id=a.mission ORDER BY l.id DESC LIMIT 50""",(verification.MAX_BYTES,DETAIL_LIMIT)):
        data=decode(row['payload']);status=status_of(data)
        if any(data.get(k)!=row[k] for k in ('status','sha256','profile','revision','size')):status='unreadable'
        metrics={}
        raw=data.get('metrics')
        if isinstance(raw,dict):
            for key in ('tp','fp','fn','recall','false_alert_share'):
                v=raw.get(key)
                if type(v) in (float,int) and 0<=v<= (1 if key in ('recall','false_alert_share') else 100000):
                    metrics[key]=v
        result.append({'kind':'laboratory',**{k:row[k] for k in ('id','artifact','created','profile','revision','size','name','version','source_mission','mode')},
            'status':status,'identity':identity(row['content'],row['sha256']),'metrics':metrics,'limit':laboratory.LIMIT})
    return result
