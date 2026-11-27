"""Hypothetical opportunity assessments and ranking; caller owns the transaction.

Scores are not demand probabilities or authorizations to launch a business.
"""

def opportunity_hash(o,*,digest):
    return digest({k:o[k] for k in ('title','body','next_test')})

def assess(c,mid,agent,target,text,*,decode,source,page_reference,opportunity_hash,canonical):
    if agent!='MIDAS' or not target.isdigit() or len(target)>12:raise ValueError('Évaluation MIDAS, ID opportunité requis')
    o=c.execute('SELECT * FROM opportunities WHERE id=? AND mission=?',(int(target),mid)).fetchone()
    if not o:raise ValueError('Opportunité de cette mission requise')
    if c.execute('SELECT COUNT(*) FROM market_assessments WHERE mission=?',(mid,)).fetchone()[0]>=6:raise ValueError('Plafond de six évaluations par mission')
    try:d=decode(text)
    except (ValueError,TypeError,RecursionError):raise ValueError('JSON économique invalide') from None
    fields={'price_cents','variable_cost_cents','fixed_month_cents','monthly_units','automation_pct','risk','source_runs','rationale'}
    if not isinstance(d,dict) or not fields<=set(d) or set(d)-fields-{'page_refs'}:raise ValueError('Champs d’évaluation incomplets')
    for k,lo,hi in [('price_cents',1,10000000),('variable_cost_cents',0,10000000),('fixed_month_cents',0,100000000),('monthly_units',1,100000),('automation_pct',0,100),('risk',1,5)]:
        if type(d[k]) is not int or not lo<=d[k]<=hi:raise ValueError('Hypothèse hors limite : '+k)
    if not isinstance(d['rationale'],str) or not 20<=len(d['rationale'])<=1200:raise ValueError('Justification de 20 à 1200 caractères')
    ids=d['source_runs']
    if not isinstance(ids,list) or len(ids)>3 or any(type(i) is not int or not 1<=i<=9007199254740991 for i in ids) or len(set(ids))!=len(ids):raise ValueError('Références de source invalides')
    for rid in ids:source(c,rid,mid)
    pages=d.get('page_refs',[])
    if not isinstance(pages,list) or len(pages)>5 or any(type(x) is not int or not 1<=x<=9007199254740991 for x in pages) or len(set(pages))!=len(pages):raise ValueError('Références de pages invalides')
    page_evidence=[page_reference(c,mid,p) for p in pages]
    price=d['price_cents'];contribution=price-d['variable_cost_cents'];fixed=d['fixed_month_cents'];units=d['monthly_units']
    margin_bp=contribution*10000//price
    breakeven=(fixed+contribution-1)//contribution if contribution>0 else None
    monthly=contribution*units-fixed
    # Score 0–100, deliberately not a demand probability. Macro evidence is separate.
    components={'margin':max(0,min(40,margin_bp*40//10000)),
                'scenario':max(0,min(20,monthly*20//(price*units))),
                'automation':d['automation_pct']*25//100,'risk':(5-d['risk'])*15//4}
    result={'score':sum(components.values()) if contribution>0 and monthly>0 else 0,'components':components,'contribution_cents':contribution,'margin_bp':margin_bp,'breakeven_units':breakeven,'monthly_result_cents':monthly,'scenario_viable':contribution>0 and monthly>0,'evidence_count':len(ids),'page_count':len(pages),'pages':page_evidence,'classification':'hypothèse non validée','limit':'EUR hors TVA; hypothèses agent non certifiées. Coût variable doit inclure acquisition, frais, retours, cotisations, assistance; fixe inclut exploitation. Résultat avant impôt et rémunération propriétaire si non inclus. Aucune preuve de ventes.'}
    rid=c.execute('INSERT INTO market_assessments(opportunity,mission,agent,opportunity_sha256,assumptions,source_runs,result) VALUES(?,?,?,?,?,?,?)',(o['id'],mid,agent,opportunity_hash(o),canonical(d),canonical(ids),canonical(result))).lastrowid
    return {'assessment':rid,'opportunity':o['id'],**result}

def ranking(c,*,opportunity_hash,decode,source,page_reference):
    out=[]
    for r in c.execute("""SELECT a.*,o.title,o.body,o.next_test,p.id AS project FROM market_assessments a
        JOIN opportunities o ON o.id=a.opportunity JOIN missions m ON m.id=a.mission
        LEFT JOIN projects p ON p.opportunity=o.id
        WHERE m.mode='cloud' AND m.state='terminée' AND (p.id IS NULL OR p.state='active')
        AND a.id=(SELECT MAX(b.id) FROM market_assessments b WHERE b.opportunity=a.opportunity)
        ORDER BY a.id DESC"""):
        if opportunity_hash(r)!=r['opportunity_sha256']:continue
        try:
            for rid in decode(r['source_runs']):source(c,rid,r['mission'])
            res=decode(r['result'])
            if any(page_reference(c,r['mission'],p['id'])!=p for p in res.get('pages',[])):continue
        except ValueError:continue
        out.append({'id':r['id'],'opportunity':r['opportunity'],'mission':r['mission'],'project':r['project'],'title':r['title'],'created':r['created'],'assumptions':decode(r['assumptions']),'result':decode(r['result'])})
    return sorted(out,key=lambda r:(-r['result']['score'],r['opportunity']))

