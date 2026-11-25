"""Read-only collective facts, separate from agent reports and commercial evidence."""
import hashlib
import json
import re
import intelligence as intel
import n8n_bridge as n8n

LIMIT='Faits locaux enregistrés, pas certification externe. Contrôles de texte limités à quelques contradictions explicites; absence d’alerte ne certifie pas un rapport. Aucune preuve de demande ou de vente.'

def _finding(code, **fields):
    return {'code':code, **fields}

def assessment(c,row):
    """Validate the latest assessment against its exact opportunity and source references."""
    d=intel.decode(row['assumptions'])
    result=intel.decode(row['result'])
    if intel.opportunity_hash(row)!=row['opportunity_sha256']:
        raise ValueError('Opportunité modifiée depuis évaluation')
    ids=intel.decode(row['source_runs'])
    if ids!=d['source_runs']:raise ValueError('Références incohérentes')
    for rid in ids:intel.source(c,rid,row['mission'])
    pages=[intel.page_reference(c,row['mission'],pid) for pid in d.get('page_refs',[])]
    if pages!=result['pages']:raise ValueError('Pages modifiées')
    price=d['price_cents'];units=d['monthly_units'];fixed=d['fixed_month_cents']
    contribution=price-d['variable_cost_cents'];monthly=contribution*units-fixed
    margin=contribution*10000//price
    components={'margin':max(0,min(40,margin*40//10000)),
        'scenario':max(0,min(20,monthly*20//(price*units))),
        'automation':d['automation_pct']*25//100,'risk':(5-d['risk'])*15//4}
    viable=contribution>0 and monthly>0
    expected={'score':sum(components.values()) if viable else 0,'components':components,
        'contribution_cents':contribution,'margin_bp':margin,
        'breakeven_units':(fixed+contribution-1)//contribution if contribution>0 else None,
        'monthly_result_cents':monthly,'scenario_viable':viable,'evidence_count':len(ids),
        'page_count':len(pages),'classification':'hypothèse non validée'}
    if any(result.get(k)!=v for k,v in expected.items()):raise ValueError('Calcul enregistré incohérent')
    return {'id':row['assessment_id'],'agent':row['assessment_agent'],
        'assumptions':{k:d[k] for k in ('price_cents','variable_cost_cents','fixed_month_cents',
            'monthly_units','automation_pct','risk','source_runs')},
        'page_refs':d.get('page_refs',[]),'result':expected}

def registry(c,mid,compact=False):
    """Mission-scoped, includes runs from other agents, never owner tests or secrets."""
    findings=[];runs=[];opps=[]
    mission=c.execute('SELECT mode FROM missions WHERE id=?',(mid,)).fetchone()
    if not mission:raise ValueError('Mission absente')
    link=c.execute('SELECT kind FROM campaign_missions WHERE mission=?',(mid,)).fetchone()
    opportunity_expected=bool(link and link['kind']=='opportunity')
    for r in c.execute("""SELECT r.id,r.capability,r.actor,r.task,r.state,r.diagnostic,w.request_id,w.execution_id,w.result
        FROM connector_runs r LEFT JOIN connector_workflow_results w ON w.run=r.id
        WHERE r.mission=? ORDER BY r.id""",(mid,)):
        item={k:r[k] for k in ('id','capability','actor','task','state','diagnostic')}
        if r['state']=='received':
            try:
                if r['capability']==intel.CAP:
                    snapshot=intel.source(c,r['id'],mid)
                    item.update(integrity=True,year=snapshot['year'],countries=snapshot['countries'])
                elif r['capability']==n8n.COMPARE:
                    d=intel.decode(r['result']);ref=d['source_run']
                    payload=intel.compare_input(c,intel.canonical({'source_run':ref}),mid)
                    if (d['request_id']!=r['request_id'] or d['execution_id']!=r['execution_id'] or
                        d['protocol']!=n8n.PROTOCOL or d['payload_sha256']!=hashlib.sha256(payload.encode()).hexdigest() or
                        intel.canonical(d['result'])!=intel.canonical(n8n.expected(n8n.COMPARE,payload))):
                        raise ValueError('Contrat de comparaison incohérent')
                    item.update(integrity=True,source_run=ref,execution_id=r['execution_id'],markets=d['result']['markets'])
                elif r['capability'] in (n8n.HEALTH,n8n.METRICS):
                    d=intel.decode(r['result'])
                    if d['request_id']!=r['request_id'] or d['execution_id']!=r['execution_id'] or d['protocol']!=n8n.PROTOCOL:
                        raise ValueError('Contrat de résultat incohérent')
                    item.update(execution_id=r['execution_id'],result=d['result'])
                    # Input is not persisted; don't claim recomputation.
            except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
                item['integrity']=False
                findings.append(_finding('connector_integrity',run=r['id'],capability=r['capability']))
        elif r['state'] in ('failed','unknown','reserved'):
            findings.append(_finding('connector_unconfirmed',run=r['id'],state=r['state']))
        runs.append(item)
    for row in c.execute("""SELECT o.*,a.id AS assessment_id,a.agent AS assessment_agent,a.assumptions,a.source_runs,a.result,a.opportunity_sha256
        FROM opportunities o LEFT JOIN market_assessments a ON a.id=(SELECT MAX(b.id) FROM market_assessments b
        WHERE b.opportunity=o.id AND b.mission=o.mission) WHERE o.mission=? ORDER BY o.id""",(mid,)):
        item={k:row[k] for k in ('id','title','status')}
        item['assessment']=None
        if row['assessment_id'] is None:
            if opportunity_expected:findings.append(_finding('opportunity_unassessed',opportunity=row['id']))
        else:
            try:item['assessment']=assessment(c,row)
            except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
                findings.append(_finding('assessment_integrity',opportunity=row['id'],assessment=row['assessment_id']))
        opps.append(item)
    valid_compare=[x['id'] for x in runs if x['capability']==n8n.COMPARE and x.get('integrity') is True]
    # Explicit lexical hints only. Never silently rewrite a report or declare general semantic consistency.
    if valid_compare:
        for row in c.execute('SELECT id,agent,report FROM reports WHERE mission=? ORDER BY id',(mid,)):
            try:
                text=intel.decode(row['report'])['rapport'].lower().replace('’',"'")
                # Match the two narrow false-negative formulations observed in the historical campaign.
                if re.search(r"\bn8n(?:\.market_compare)?\x60?\s+n[' ]a pas été appelé\b|\baucun résultat n8n n[' ]est attesté\b",text):
                    findings.append(_finding('possible_n8n_report_contradiction',report=row['id'],agent=row['agent'],runs=valid_compare))
            except (ValueError,TypeError,KeyError,AttributeError):
                findings.append(_finding('report_unreadable',report=row['id']))
    auditors=[dict(r) for r in c.execute("SELECT id,state FROM tasks WHERE mission=? AND agent='SENTINEL' ORDER BY id",(mid,))]
    proof={'mission':mid,'mode':mission['mode'],'connector_count':len(runs),'opportunity_count':len(opps),
        'assessed_count':sum(x['assessment'] is not None for x in opps),'finding_count':len(findings),
        'connectors':runs,'opportunities':opps,'findings':findings,'sentinel_tasks':auditors,
        'review_required':bool(findings),'limit':LIMIT}
    if compact:
        # Bounded context. Preserve counts and signal omitted rows; prefer newest facts.
        for key,cap in (('connectors',12),('opportunities',20),('findings',16),('sentinel_tasks',6)):
            if len(proof[key])>cap:
                proof[key+'_omitted']=len(proof[key])-cap
                proof[key]=proof[key][-cap:]
    return proof

def previous_laboratory(c):
    """Recent genuine laboratory evidence, context only; do not infer product equivalence."""
    out=[]
    for row in c.execute("""SELECT l.id,l.artifact,l.profile,l.revision,l.size,l.sha256,l.status,
        a.name,a.version,a.content,a.mission FROM laboratory_runs l JOIN artifacts a ON a.id=l.artifact
        JOIN missions m ON m.id=a.mission WHERE m.mode='cloud' AND m.state='terminée'
        AND a.agent='NEXUS' ORDER BY l.id DESC LIMIT 6"""):
        if hashlib.sha256(row['content'].encode()).hexdigest()!=row['sha256']:continue
        out.append({k:row[k] for k in ('id','artifact','profile','revision','size','sha256','status','name','version','mission')})
    return out

def campaign_summary(c,campaign):
    """Advisory audit for the current campaign. Recomputed without writes or providers."""
    if not campaign:return None
    rows=[]
    for m in campaign['missions']:
        if m['kind'] not in ('opportunity','market'):continue
        v=registry(c,m['id'])
        rows.append({k:v[k] for k in ('mission','connector_count','opportunity_count','assessed_count',
            'finding_count','review_required','sentinel_tasks')})
    return {'missions':rows,'finding_count':sum(v['finding_count'] for v in rows),
        'review_required':any(v['review_required'] for v in rows),'limit':LIMIT} if rows else None
