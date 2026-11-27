"""Reproducible synthetic catalogue fixtures and independent scoring.
No process, database, network or product execution. The caller owns authorization.
"""

def catalogue(size,seed,*,sizes,random,encode):
    """Expected alerts are derived from injected faults, not the product's output."""
    if type(size) is not int or size not in sizes or type(seed) is not int or not 0<=seed<=2147483647:
        raise ValueError('Taille ou graine hors limites')
    rng=random.Random(seed)
    locales=['fr-FR','en-GB']
    healthy=[{'sku':f'S{i:04d}','locale':loc,'title':'T'} for i in range(size//2) for loc in locales]
    dirty=[dict(r) for r in healthy]
    duplicates=set(rng.sample(range(size//2),size*4//100))
    missing_title=set(rng.sample(range(size),size*6//100))
    for i in duplicates:dirty[i*2+1]['locale']='fr-FR'
    for i in missing_title:dirty[i]['title']=''
    alerts=[f"P1 | CHAMP_REQUIS | ligne {i+1} | SKU {dirty[i]['sku']} | locale {dirty[i]['locale']} | title" for i in sorted(missing_title)]
    alerts += [f'P1 | DOUBLON | ligne {i*2+2} | SKU S{i:04d} | locale fr-FR | première ligne {i*2+1}' for i in sorted(duplicates)]
    alerts += [f'P2 | LOCALE_MANQUANTE | SKU S{i:04d} | locale en-GB' for i in sorted(duplicates)]
    total=f'TOTAL | P1 {len(missing_title)+len(duplicates)} | P2 {len(duplicates)}'
    return [
        {'name':'sain','input':encode({'locales':locales,'rows':healthy}),'expected':[],'total':'TOTAL | P1 0 | P2 0'},
        {'name':'anomalies','input':encode({'locales':locales,'rows':dirty}),'expected':alerts,'total':total},
        {'name':'refus','input':encode({'locales':['fr-FR'],'rows':[{'sku':' ','locale':'fr-FR','title':'T'}]}),'expected_error':'ERREUR | SKU ou locale invalide à la ligne 1.'}
    ]


def score(fixtures,observed,*,collections,math):
    cases=[];tp=fp=fn=0;valid=True;infra=False
    if not isinstance(observed,list) or len(observed)!=len(fixtures):raise RuntimeError('Résultat laboratoire incomplet')
    for f,r in zip(fixtures,observed):
        if not isinstance(r,dict) or r.get('name')!=f['name'] or type(r.get('passed')) is not bool:
            raise RuntimeError('Résultat laboratoire incohérent')
        if not r['passed']:
            infra=True;cases.append({'name':f['name'],'status':'unavailable','error':str(r.get('error','Capture impossible'))[:200]});continue
        output=r.get('output');ms=r.get('elapsed_ms')
        if not isinstance(output,str) or len(output.encode('utf8'))>24000 or type(ms) not in (float,int) or not math.isfinite(ms) or not 0<=ms<=10000:
            raise RuntimeError('Capture laboratoire invalide')
        base={'name':f['name'],'output':output,'elapsed_ms':ms}
        if 'expected_error' in f:
            passed=output==f['expected_error']
            valid &= passed
            cases.append({**base,'status':'passed' if passed else 'failed','expected_error':f['expected_error']});continue
        lines=output.splitlines()
        totals=[line for line in lines if line.startswith('TOTAL |')]
        actual=[line for line in lines if not line.startswith('TOTAL |')]
        expected=collections.Counter(f['expected']);actual=collections.Counter(actual)
        good=sum((expected&actual).values());false=sum((actual-expected).values());miss=sum((expected-actual).values())
        tp+=good;fp+=false;fn+=miss
        p1=sum(n for x,n in actual.items() if x.startswith('P1 | '));p2=sum(n for x,n in actual.items() if x.startswith('P2 | '))
        totals_ok=totals==[f'TOTAL | P1 {p1} | P2 {p2}'] and bool(lines) and lines[-1]==totals[0]
        # Invalid or unexpected report format is never a passing measurement.
        format_ok=totals_ok and all(x.startswith(('P1 | ','P2 | ')) for x in actual)
        valid &= format_ok
        cases.append({**base,'status':'passed' if format_ok and not false and not miss else 'failed','tp':good,'fp':false,'fn':miss,'expected':f['expected'],'expected_total':f['total'],'totals_ok':totals_ok})
    if infra:return {'status':'unavailable','cases':cases,'metrics':None}
    recall=tp/(tp+fn) if tp+fn else None
    fdr=fp/(tp+fp) if tp+fp else None
    passed=valid and recall is not None and recall>=.95 and fdr is not None and fdr<=.05
    return {'status':'passed' if passed else 'failed','cases':cases,'metrics':{'tp':tp,'fp':fp,'fn':fn,'recall':recall,'false_alert_share':fdr,'format_and_refusal_ok':bool(valid),'thresholds':{'recall_min':.95,'false_alert_share_max':.05}}}
