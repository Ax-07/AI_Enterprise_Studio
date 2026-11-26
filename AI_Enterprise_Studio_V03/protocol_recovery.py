"""Protocol recovery without extra turns, extra authorization or invented evidence."""
import json

def invalid_events(c,mid,tid):
    out=[]
    for row in c.execute("SELECT id,result FROM events WHERE mission=? AND task=? AND action='test_file' ORDER BY id DESC LIMIT 8",(mid,tid)):
        try:
            r=json.loads(row['result'])
            if r.get('status')=='invalid':out.append({'event':row['id'],'proof':r.get('verification_id'),'error':r.get('error','Protocole invalide')})
        except (ValueError,TypeError,AttributeError):continue
    return out

def last_read(c,t):
    # Immutable SQLite artifact, reintroduced without another paid tool-selection turn.
    for row in c.execute("SELECT result FROM events WHERE mission=? AND task=? AND action='read_file' AND ok=1 ORDER BY id DESC LIMIT 8",(t['mission'],t['id'])):
        try:
            r=json.loads(row['result'])
            data=r.get('contenu');aid=r.get('fichier')
            if not isinstance(data,str) or len(data.encode('utf8'))>24000:continue
            artifact=c.execute("""SELECT a.* FROM artifacts a WHERE a.id=? AND (a.mission=? OR a.id IN
                (SELECT artifact FROM mission_artifact_refs WHERE mission=?))""",(aid,t['mission'],t['mission'])).fetchone()
            if artifact and artifact['content']==data:
                return {'fichier':aid,'nom':artifact['name'],'version':artifact['version'],'contenu':data}
        except (ValueError,TypeError,AttributeError):continue
    return None

def corrective(c,t):
    if t['agent'] not in ('SENTINEL','NEXUS'):return False
    # Only restrict after invalid protocol, until a new actual test result is recorded.
    for e in c.execute("SELECT result FROM events WHERE mission=? AND task=? AND action='test_file' ORDER BY id DESC LIMIT 1",(t['mission'],t['id'])):
        try:
            r=json.loads(e['result'])
            return r.get('kind')=='html' and r.get('status')=='invalid'
        except (ValueError,TypeError,AttributeError):return False
    return False

def recovery_task(c,mid,cfg):
    m=c.execute("SELECT * FROM missions WHERE id=? AND state='bloquée' AND engine='dynamic' AND mode='cloud'",(mid,)).fetchone()
    if not m:return None
    t=c.execute("""SELECT * FROM tasks t WHERE mission=? AND state='prête' AND NOT EXISTS
        (SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    if not t or t['agent']!='SENTINEL' or t['turns']+1>=cfg['turn_limit']:return None
    if not m['error'].startswith('Action identique répétée trois fois; tâche #'+str(t['id'])+' ; outil read_file ; cible '):return None
    pinned=last_read(c,t)
    if not corrective(c,t) or not pinned or not pinned['nom'].lower().endswith('.html'):return None
    if m['error']!='Action identique répétée trois fois; tâche #'+str(t['id'])+' ; outil read_file ; cible ref:'+str(pinned['fichier']):return None
    last=c.execute("SELECT result FROM events WHERE mission=? AND task=? AND action='test_file' ORDER BY id DESC LIMIT 1",(mid,t['id'])).fetchone()
    try:
        v=json.loads(last['result']); proof=c.execute('SELECT * FROM verification_results WHERE id=? AND mission=? AND artifact=? AND agent=?',(v['verification_id'],mid,pinned['fichier'],t['agent'])).fetchone()
        if not proof or json.loads(proof['result']).get('status')!='invalid':return None
    except (ValueError,TypeError,KeyError,AttributeError):return None
    if c.execute('SELECT COUNT(*) FROM events WHERE mission=?',(mid,)).fetchone()[0]>=cfg['call_limit']:return None
    return t['id']
