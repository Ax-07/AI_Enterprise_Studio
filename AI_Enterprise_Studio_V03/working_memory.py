"""Task-local working memory reconstructed from persisted, untrusted tool results.
No model, network, new storage, or modification of historical events.
"""
import json,re
import protocol_recovery

MAX_MEMORY=3
MAX_FILE_BYTES=28000
def obj(raw):
    try:
        v=json.loads(raw)
        return v if isinstance(v,dict) else {}
    except (TypeError,ValueError):return {}

def snapshot(c,t):
    mid=t['mission'];tid=t['id'];files=[];reports=[];hits=[];seen=set();remaining=MAX_FILE_BYTES
    mem_count=0;read_counts={};report_counts={};memory_queries=[]
    for e in c.execute("SELECT action,args,result,ok FROM events WHERE mission=? AND task=? AND agent=? ORDER BY id DESC",(mid,tid,t['agent'])):
        action=e['action'];r=obj(e['result']);args=obj(e['args'])
        if action=='memory':
            mem_count+=1
            q=args.get('text','')
            if isinstance(q,str):memory_queries.append(q[:200])
        if not e['ok']:continue
        if action=='read_file':
            aid=r.get('fichier');data=r.get('contenu')
            if type(aid) is not int or not isinstance(data,str):continue
            row=c.execute("""SELECT * FROM artifacts WHERE id=? AND (mission=? OR id IN
                (SELECT artifact FROM mission_artifact_refs WHERE mission=?))""",(aid,mid,mid)).fetchone()
            if not row or row['content']!=data:continue
            read_counts[aid]=read_counts.get(aid,0)+1
            if len(files)<2 and aid not in {x['fichier'] for x in files} and len(data.encode('utf8'))<=min(24000,remaining):
                files.append({'fichier':aid,'nom':row['name'],'version':row['version'],'contenu':data})
                remaining-=len(data.encode('utf8'))
        elif action=='read_report':
            rid=r.get('rapport_id')
            if type(rid) is not int:continue
            report_counts[rid]=report_counts.get(rid,0)+1
            if len(reports)<2 and rid not in {x['rapport_id'] for x in reports}:
                raw=json.dumps(r,ensure_ascii=False)
                reports.append({'rapport_id':rid,'extrait':raw[:4000],'partiel':len(raw)>4000})
        elif action=='memory':
            for hit in r.get('résultats',[]) if isinstance(r.get('résultats'),list) else []:
                if not isinstance(hit,dict):continue
                key=(str(hit.get('type')),str(hit.get('id')))
                if key in seen or len(hits)>=8:continue
                seen.add(key)
                hits.append({**{k:hit.get(k) for k in ('type','id','mission','mode')},'extrait':str(hit.get('extrait',''))[:700],'partiel':True})
    return {'files':files,'reports':reports,'hits':hits,'memory_count':mem_count,'queries':memory_queries[:3],
            'read_counts':read_counts,'report_counts':report_counts}

def policy(c,t,cfg,allowed,w):
    allowed=set(allowed);mid=t['mission']
    if w['memory_count']>=MAX_MEMORY:allowed.discard('memory')
    if 'search' in allowed and (not cfg.get('brave') or
       c.execute('SELECT COUNT(*) FROM searches').fetchone()[0]>=cfg['limit'] or
       c.execute('SELECT COUNT(*) FROM searches WHERE mission=?',(mid,)).fetchone()[0]>=cfg['mission_search_limit']):
        allowed.discard('search')
    # Reading a public page requires a previously retrieved search result.
    if 'read' in allowed and not c.execute("SELECT 1 FROM searches WHERE mission=? AND status='reçue'",(mid,)).fetchone():
        allowed.discard('read')
    ids={r[0] for r in c.execute("""SELECT a.id FROM artifacts a WHERE a.mission=? AND a.version=
        (SELECT MAX(b.version) FROM artifacts b WHERE b.mission=a.mission AND b.name=a.name)
        UNION SELECT artifact FROM mission_artifact_refs WHERE mission=?""",(mid,mid))}
    if ids and ids<={x['fichier'] for x in w['files']}:allowed.discard('read_file')
    return allowed

def redundant(c,t,v,w,resolve):
    action=v['action'];target=v['target'].strip()
    if action=='read_file':
        try:row,_=resolve(c,t['mission'],target)
        except ValueError:return False
        return bool(row and row['id'] in {x['fichier'] for x in w['files']})
    if action=='read_report' and target.isdigit() and len(target)<=12:
        return any(x['rapport_id']==int(target) and not x['partiel'] for x in w['reports'])
    return False

def recovery_task(c,mid,cfg):
    mission=c.execute("SELECT * FROM missions WHERE id=? AND state='bloquée' AND mode='cloud' AND engine='dynamic'",(mid,)).fetchone()
    if not mission:return None
    t=c.execute("""SELECT * FROM tasks t WHERE mission=? AND state='prête' AND NOT EXISTS
        (SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    if not t or t['turns']>=cfg['turn_limit'] or protocol_recovery.corrective(c,t):return None
    match=re.fullmatch(r'Action identique répétée trois fois; tâche #(\d+) ; outil read_file ; cible (.+)',mission['error'] or '')
    if not match or int(match[1])!=t['id']:return None
    if t['agent']=='ATLAS' and not c.execute('SELECT 1 FROM tasks WHERE parent=?',(t['id'],)).fetchone():return None
    w=snapshot(c,t);target=match[2]
    # Match successful identical target events to the same immutable file currently pinned.
    for f in w['files']:
        aid=f['fichier']
        if w['read_counts'].get(aid,0)<2:continue
        if target.startswith('ref:'):
            if target!='ref:'+str(aid):continue
            if not c.execute('SELECT 1 FROM mission_artifact_refs WHERE mission=? AND artifact=?',(mid,aid)).fetchone():continue
        else:
            current=c.execute('SELECT id FROM artifacts WHERE mission=? AND name=? ORDER BY version DESC LIMIT 1',(mid,target)).fetchone()
            if not current or current[0]!=aid:continue
        count=0
        for e in c.execute("SELECT args,result FROM events WHERE mission=? AND task=? AND agent=? AND action='read_file' AND ok=1",(mid,t['id'],t['agent'])):
            if obj(e['args']).get('target')==target and obj(e['result']).get('fichier')==aid:count+=1
        if count<2:continue
        if c.execute('SELECT COUNT(*) FROM events WHERE mission=?',(mid,)).fetchone()[0]>=cfg['call_limit']:return None
        calls,spent=c.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger WHERE mission=?',(mid,)).fetchone()
        if calls>=cfg['call_limit'] or spent>=cfg['mission_budget']:return None
        return t['id']
    return None
