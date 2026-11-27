"""Read-only commercial offer qualification and observation eligibility.
An internal proposal or observation protocol is never a sale authorization.
"""

def offer_status(c,row,*,intel,signal,research,portfolio,hashlib,urlsplit,commercial_economics,economics_result,limit):
    plan=intel.decode(row['plan']);pid=row['project'];mid=row['mission']
    evidence=[];invalid=[]
    for sid in plan['signal_ids']:
        try:
            s,p=signal(c,pid,sid,mid)
            excerpt=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(s['page'],)).fetchone()[0])['texte']
            evidence.append({'id':sid,'kind':s['kind'],'proof':p,'quote':s['quote'],'interpretation':s['interpretation'],'quality':research.excerpt_quality(excerpt)})
        except (ValueError,TypeError,KeyError,AttributeError):invalid.append(sid)
    eco=c.execute('SELECT * FROM commercial_economics WHERE offer=?',(row['id'],)).fetchone()
    review=c.execute('SELECT * FROM commercial_reviews WHERE offer=?',(row['id'],)).fetchone()
    art=portfolio.latest(c,pid);proofs=[];lab=None
    exact=bool(art and art['id']==row['artifact'] and hashlib.sha256(art['content'].encode()).hexdigest()==row['artifact_sha256'])
    if exact:
        proofs=portfolio.evidence(c,art);lab=portfolio.laboratory.canonical(c,art)
    independent=any(p['agent']=='SENTINEL' and p['status']=='passed' for p in proofs) and not any(p['agent']=='SENTINEL' and p['status']=='failed' for p in proofs)
    if exact and portfolio.laboratory.supports(art):independent=independent and bool(lab and lab['status']=='passed')
    usable=[x for x in evidence if x['quality']=='text_available']
    domains={urlsplit(x['proof']['url']).hostname for x in usable}
    kinds={x['kind'] for x in usable}
    economics={'id':eco['id'],'assumptions':intel.decode(eco['assumptions']),'result':intel.decode(eco['result'])} if eco else None
    if economics:
        economics['adverse_parameters']=commercial_economics.adverse_parameters(plan,economics['assumptions'])
    audit={'id':review['id'],**intel.decode(review['review'])} if review else None
    gaps=[]
    if not independent:gaps.append('preuve_technique_independante_manquante')
    if invalid:gaps.append('signaux_invalides')
    if len(domains)<2 or 'buyer_problem' not in kinds or not kinds.intersection({'competitor_offer','competitor_price','alternative'}):gaps.append('indices_documentaires_insuffisants')
    if not economics or economics['result']!=economics_result(plan,economics['assumptions']) or economics['result']['monthly_result_cents']<=0 or economics['result']['contribution_cents']<=0:gaps.append('scenario_economique_manquant_ou_defavorable')
    if not audit or audit['verdict']!='propose_future_test':gaps.append('revue_independante_manquante_ou_reserves')
    m=c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()
    if m['state']!='terminée':gaps.append('mission_non_terminee')
    origin=c.execute("""SELECT base_offer FROM commercial_followups WHERE resulting_offer=?
        UNION ALL SELECT f.base_offer FROM commercial_followup_retries r JOIN commercial_followups f ON f.campaign=r.original_campaign WHERE r.resulting_offer=?""",(row['id'],row['id'])).fetchone()
    return {'id':row['id'],'base_offer':origin['base_offer'] if origin else None,'project':pid,'mission':mid,'artifact':row['artifact'],'artifact_sha256':row['artifact_sha256'],
        'plan':plan,'evidence':evidence,'invalid_signal_ids':invalid,'economics':economics,'review':audit,
        'technical_proofs':proofs,'laboratory':lab,'gaps':gaps,
        'state':'proposition_a_examiner' if not gaps else 'preparation_incomplete',
        'observations':0,'sales':0,'commercial_spend_cents':0,'external_authorized':False,'limit':limit}


def gate(c,row,*,commercial,portfolio):
    v=commercial.offer_status(c,row);p=portfolio.project(c,row['project'])
    latest=commercial.project_status(c,row['project'])['offer']
    reasons=list(v['gaps'])
    if not p or p['state']!='active':reasons.append('activité inactive')
    if not latest or latest['id']!=row['id']:reasons.append('offre remplacée')
    # Documentary/review gaps may justify an observation-only protocol, never a sale.
    permitted_gaps={'indices_documentaires_insuffisants','revue_independante_manquante_ou_reserves'}
    review=(v['review'] or {}).get('verdict')
    eligible=bool(p and p['state']=='active' and latest and latest['id']==row['id'] and row['artifact'] and
                  set(v['gaps'])<=permitted_gaps and review in ('study_further','propose_future_test'))
    return v,eligible,reasons


def frozen(v):
    return {k:v[k] for k in ('id','project','mission','artifact','artifact_sha256','plan','economics','review','gaps','state')}
