"""Bounded comparison of product versions; no persistence or promotion authority.
Execution callbacks are supplied by the legacy authorized caller.
"""

def feature_spec():
    # Product must import a real CSV file, not just reproduce the example in its JSON textarea.
    def one(name,csv,out):
        return {'name':name,'steps':[{'op':'upload','selector':'#csv-file','value':csv},
            {'op':'click','selector':'#import-csv'},{'op':'click','selector':'#run'},
            {'op':'text_equals','selector':'#out','value':out}]}
    return {'cases':[
        one('CSV sain','sku,locale,title\nZ9,fr-FR,Chaise\nZ9,en-GB,Chair\n','TOTAL | P1 0 | P2 0'),
        one('CSV anomalies','sku,locale,title\nX7,fr-FR,\nX7,fr-FR,Table\n',
            'P1 | CHAMP_REQUIS | ligne 1 | SKU X7 | locale fr-FR | title\nP1 | DOUBLON | ligne 2 | SKU X7 | locale fr-FR | première ligne 1\nP2 | LOCALE_MANQUANTE | SKU X7 | locale en-GB\nTOTAL | P1 2 | P2 1')]}


def verify_pair(base,new,frozen,profile,cfg,lab_before,*,verification,laboratory,feature_spec,json,limit,csv_profile):
    """Re-run identical trusted contracts; compare quality, report timing but never optimize noise."""
    enabled=cfg.get('html_sandbox_enabled',False)
    result={'limit':limit,'replays':[],'laboratory':None,'feature':None}
    ok=True
    for spec in frozen['replays']:
        r=verification.run(new['name'],new['content'],spec['spec'],enabled)
        result['replays'].append({'proof':spec['proof'],'result':r})
        if r['status']!='passed':ok=False
    if frozen['lab'] is not None:
        r=laboratory.evaluate(new,laboratory.PROFILE,300,laboratory.DEFAULT_SEED,enabled)
        old=lab_before.get('metrics') if lab_before else None;newm=r.get('metrics')
        comparable=bool(lab_before and lab_before['status']=='passed' and r['status']=='passed' and old and newm and
            r['fixture_sha256']==lab_before.get('fixture_sha256') and newm['recall']>=old['recall'] and
            newm['false_alert_share']<=old['false_alert_share'] and newm['format_and_refusal_ok'])
        result['laboratory']={'baseline_run':frozen['lab'],'baseline_metrics':old,'candidate':r,'non_regression':comparable,
            'baseline_times':[{ 'name':x['name'],'elapsed_ms':x['elapsed_ms']} for x in (lab_before or {}).get('cases',[]) if 'elapsed_ms' in x]}
        ok &= comparable
    if profile==csv_profile and ok:
        raw=json.dumps(feature_spec(),ensure_ascii=False)
        before=verification.run(base['name'],base['content'],raw,enabled)
        after=verification.run(new['name'],new['content'],raw,enabled)
        result['feature']={'spec':feature_spec(),'baseline':before,'candidate':after}
        # Baseline must genuinely fail this new contract; unavailable is not a comparison.
        if before['status']=='failed' and after['status']=='passed':return 'retained',result
        if after['status']!='passed':return 'rejected',result
        return 'review',result
    return ('review' if ok else 'rejected'),result
