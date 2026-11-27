"""Independent verification of historical marketing evidence and exact claims.
Read only; no publication or legal approval authority.
"""

def evidence(c,did,*,ac,lab,json,b):
    row=ac._row(c,did)
    if ac.state(c,row)!='draft':raise ValueError('Brouillon périmé')
    offer=ac._offer(c,row['offer'])
    art=c.execute('SELECT a.* FROM artifacts a JOIN missions m ON m.id=a.mission WHERE a.id=(SELECT artifact FROM commercial_offers WHERE id=?) AND a.agent=\'NEXUS\' AND m.state=\'terminée\'',(row['offer'],)).fetchone()
    if not art or not lab.supports(art) or lab.digest(art['content'])!=offer['artifact_sha256']:
        raise ValueError('Profil marketing compatible indisponible')
    proof=lab.canonical(c,art)
    if not proof or proof['status']!='passed':raise ValueError('Benchmark exact réussi requis')
    result=json.loads(c.execute('SELECT result FROM laboratory_runs WHERE id=?',(proof['id'],)).fetchone()[0])
    fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
    if result.get('sha256')!=offer['artifact_sha256'] or result.get('fixture_sha256')!=lab.digest(lab.encode(fixtures)):
        raise ValueError('Empreinte de preuve incorrecte')
    cases=result.get('cases')
    if not isinstance(cases,list) or len(cases)!=len(fixtures) or any(x.get('status')!='passed' for x in cases):
        raise ValueError('Cas historiques incomplets')
    observed=[{'name':x['name'],'passed':True,'output':x['output'],'elapsed_ms':x['elapsed_ms']} for x in cases]
    recomputed=lab.score(fixtures,observed)
    if recomputed['status']!='passed' or recomputed['metrics']!=result.get('metrics'):
        raise ValueError('Mesures historiques incohérentes')
    metrics=recomputed['metrics']
    return {'draft':did,'offer':row['offer'],'snapshot_sha256':row['snapshot_sha256'],
            'artifact_sha256':offer['artifact_sha256'],'laboratory_run':proof['id'],
            'evidence_sha256':b.digest(result),'size':300,'price_cents':offer['plan']['price_cents'],
            'tp':metrics['tp'],'fp':metrics['fp'],'fn':metrics['fn']}


def review(c,did,payload,*,evidence,templates,b,limit):
    try:
        facts=evidence(c,did)
        expected={'classification':'internal_marketing_draft','revision':templates.REVISION,
                  'language':'fr','facts':facts,
                  'content':templates.render(facts['price_cents'],facts['size'],facts['tp'],facts['fp'],facts['fn']),
                  'limit':templates.LIMIT}
        if b.canonical(payload)!=b.canonical(expected):
            raise ValueError('Contenu ou allégation hors modèle vérifié')
        return {'state':'technical_pass','payload_sha256':b.digest(payload),'publication_authorized':False,'limit':limit}
    except (ValueError,TypeError,KeyError,AttributeError,RuntimeError,IndexError):
        return {'state':'blocked','publication_authorized':False,'limit':limit}
