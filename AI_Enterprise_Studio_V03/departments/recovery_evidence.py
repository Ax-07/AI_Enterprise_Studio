"""Historical draft eligibility and independent audit verdicts.
Read-only queries; caller owns transactions and authorization.
"""

def candidates(c,*,latest,sha,json):
    out=[]
    for a in c.execute("""SELECT a.*,m.error,ca.id AS source_campaign,pm.project
        FROM artifacts a JOIN missions m ON m.id=a.mission
        JOIN campaign_missions cm ON cm.mission=m.id JOIN campaigns ca ON ca.id=cm.campaign
        JOIN project_missions pm ON pm.mission=m.id JOIN projects p ON p.id=pm.project
        WHERE a.agent='NEXUS' AND m.mode='cloud' AND m.engine='dynamic' AND m.state='bloquée'
        AND ca.state='bloqué' AND cm.kind='create' AND p.state='active'
        AND NOT EXISTS(SELECT 1 FROM draft_recoveries d WHERE d.artifact=a.id)
        AND a.id=(SELECT MAX(b.id) FROM artifacts b WHERE b.mission=a.mission AND b.name=a.name)
        ORDER BY a.id DESC""").fetchall():
        if a['error']!='Enveloppe Autopilote insuffisante pour réserver cet appel.' and not (
            a['error'].startswith(('Enveloppe Autopilote insuffisant(e) :','Budget de mission insuffisant(e) :','Budget logiciel insuffisant(e) :')) and
            c.execute("SELECT 1 FROM budget_decisions WHERE mission=? AND decision='refused'",(a['mission'],)).fetchone()):continue
        if not a['name'].lower().endswith(('.html','.csv','.json')) or not a['content'].strip():continue
        if latest(c,a['project']):continue
        if c.execute("SELECT 1 FROM ledger WHERE mission=? AND (actual IS NULL OR state!='mesuré')",(a['mission'],)).fetchone():continue
        digest=sha(a);found=False
        for e in c.execute("SELECT args,result FROM events WHERE mission=? AND agent='NEXUS' AND action='write_file' AND ok=1",(a['mission'],)):
            try:
                args,result=json.loads(e['args']),json.loads(e['result'])
                if result.get('fichier')==a['id'] and args.get('text_sha256')==digest:found=True;break
            except (TypeError,ValueError,AttributeError):continue
        if not found:continue
        out.append({'artifact':a['id'],'name':a['name'],'sha256':digest,'source_mission':a['mission'],'source_campaign':a['source_campaign'],'project':a['project'],'size':len(a['content'])})
    return out


def verdict(c,row,*,sha,campaign,missions,proof):
    a=c.execute('SELECT * FROM artifacts WHERE id=?',(row['artifact'],)).fetchone()
    if not a or sha(a)!=row['sha256']:return 'modified'
    ca=campaign(c,row['campaign'])
    ms=missions(c,row['campaign'])
    if ca['state']=='actif':return 'active'
    if ca['state']!='terminé' or len(ms)!=1 or ms[0]['state']!='terminée' or ms[0]['artifact']!=a['id']:return 'incomplete'
    evidence=proof(c,a['id'],ms[0]['id'])
    return 'adopted' if evidence=='passed' else evidence
