"""Read-only economic views. No investment, payment, external verification or FX."""
import collective_evidence
import intelligence

LIMIT='Scénarios EUR hors TVA, hypothèses non certifiées. Résultat avant impôt et rémunération du propriétaire si non inclus. Aucune preuve de ventes, aucune allocation de capital autorisée.'
MAX_ASSESSMENTS=30
MAX_JSON=32768
BOUNDS={'price_cents':(1,10000000),'variable_cost_cents':(0,10000000),
        'fixed_month_cents':(0,100000000),'monthly_units':(1,100000),
        'automation_pct':(0,100),'risk':(1,5)}

def checked(db,row):
    if row['assessment_agent']!='MIDAS':raise ValueError('Auteur non autorisé')
    d=intelligence.decode(row['assumptions'])
    if not isinstance(d,dict):raise ValueError('Hypothèses invalides')
    for k,(lo,hi) in BOUNDS.items():
        if type(d.get(k)) is not int or not lo<=d[k]<=hi:raise ValueError('Hypothèse invalide')
    for k,cap in (('source_runs',3),('page_refs',5)):
        ids=d.get(k,[] if k=='page_refs' else None)
        if not isinstance(ids,list) or len(ids)>cap or any(type(x) is not int or not 1<=x<=9007199254740991 for x in ids) or len(set(ids))!=len(ids):raise ValueError('Références invalides')
    return collective_evidence.assessment(db,row)

def read(db,resources):
    if resources is None or type(resources.get('budget')) is not int:raise ValueError('Budget local indisponible')
    # Aggregate all persisted API reservations, including unmeasured calls.
    ledger=[dict(r) for r in db.execute("""SELECT CASE WHEN m.mode IN ('cloud','demo') THEN m.mode ELSE 'unknown' END AS mode,
        COUNT(*) AS calls,COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) AS committed,
        COALESCE(SUM(COALESCE(l.actual,0)),0) AS measured
        FROM ledger l LEFT JOIN missions m ON m.id=l.mission GROUP BY 1 ORDER BY 1""")]
    committed=sum(r['committed'] for r in ledger)
    receipts={mode:{'count':0,'gross_cents':0,'refunds_cents':0,'net_cents':0} for mode in ('test','owner_declared_live')}
    for r in db.execute("""SELECT mode,kind,COUNT(*) AS count,COALESCE(SUM(amount_cents),0) AS amount
        FROM business_receipts WHERE mode IN ('test','owner_declared_live') AND kind IN ('payment','refund') GROUP BY mode,kind"""):
        t=receipts[r['mode']];t['count']+=r['count']
        t['gross_cents' if r['kind']=='payment' else 'refunds_cents']=r['amount']
    for t in receipts.values():t['net_cents']=t['gross_cents']-t['refunds_cents']
    result=[{'kind':'summary','api_currency':'USD','receipt_currency':'EUR','budget':resources['budget'],
        'committed':committed,'remaining':max(0,resources['budget']-committed),'ledger':ledger,
        'receipts':receipts,'verified_revenue_cents':None,'actual_profit_cents':None,'actual_margin_bp':None,
        'cash_balance_cents':None,'investment_authorized':False}]
    # Latest assessment of each opportunity, including rejected/unfinished ones for transparency.
    # Only complete Cloud missions can be considered comparable; no investment decision.
    for row in db.execute("""SELECT o.id AS opportunity,o.mission,o.title,o.body,o.next_test,o.status,
        m.mode,m.state AS mission_state,a.id AS assessment_id,a.agent AS assessment_agent,a.created,
        a.opportunity_sha256,
        CASE WHEN length(CAST(a.assumptions AS BLOB))<=? THEN a.assumptions END AS assumptions,
        CASE WHEN length(CAST(a.source_runs AS BLOB))<=? THEN a.source_runs END AS source_runs,
        CASE WHEN length(CAST(a.result AS BLOB))<=? THEN a.result END AS result
        FROM market_assessments a JOIN opportunities o ON o.id=a.opportunity AND o.mission=a.mission
        JOIN missions m ON m.id=o.mission WHERE a.id=(SELECT MAX(b.id) FROM market_assessments b
            WHERE b.opportunity=o.id AND b.mission=o.mission)
        ORDER BY a.id DESC LIMIT ?""",(MAX_JSON,MAX_JSON,MAX_JSON,MAX_ASSESSMENTS)):
        item={'kind':'assessment',**{k:row[k] for k in ('assessment_id','opportunity','mission','title','mode','mission_state','created')},
              'integrity':'unavailable','scenario':None,'comparable':False,'limit':LIMIT}
        try:
            proof=checked(db,row)
            assumptions={k:proof['assumptions'][k] for k in BOUNDS}
            item.update(integrity='checked',scenario={'assumptions':assumptions,'result':proof['result']},
                        comparable=row['mode']=='cloud' and row['mission_state']=='terminée')
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,IndexError,RecursionError):
            pass
        result.append(item)
    return result
