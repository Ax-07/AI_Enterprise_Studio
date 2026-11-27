"""Read-only retrieval of historical synthetic product demonstrations.
No new benchmark, execution, publication or commercial validation.
"""

def demo(c,payload,*,lab,json):
    """Use the canonical existing synthetic benchmark, never execute an artifact here."""
    row=c.execute('SELECT a.* FROM artifacts a JOIN missions m ON m.id=a.mission WHERE a.id=(SELECT artifact FROM commercial_offers WHERE id=?) AND m.state=\'terminée\' AND a.agent=\'NEXUS\'',(payload['offer_id'],)).fetchone()
    base={'classification':'synthetic_product_demo','artifact_sha256':payload['artifact_sha256'],
          'status':'unavailable','reason':'Aucun benchmark compatible exact; ne pas inventer une démonstration.',
          'new_execution':False}
    if not row or lab.digest(row['content'])!=payload['artifact_sha256'] or not lab.supports(row):return base
    proof=lab.canonical(c,row)
    if not proof or proof['status']!='passed':return base
    run=c.execute('SELECT result FROM laboratory_runs WHERE id=?',(proof['id'],)).fetchone()
    result=json.loads(run['result'])
    fixtures=lab.catalogue(300,lab.DEFAULT_SEED)
    if result.get('fixture_sha256')!=lab.digest(lab.encode(fixtures)) or result.get('sha256')!=payload['artifact_sha256']:
        return base
    case=next((x for x in result.get('cases',[]) if x.get('name')=='anomalies' and x.get('status')=='passed'),None)
    if not case or not isinstance(case.get('output'),str):return base
    return {**base,'status':'historical_evidence','reason':'Extrait du résultat historique sur données synthétiques; pas de nouvelle exécution.',
            'laboratory_run':proof['id'],'profile':lab.PROFILE,'size':300,'seed':lab.DEFAULT_SEED,
            'input_json':fixtures[1]['input'],'observed_output':case['output'],
            'metrics':proof['metrics'],'limit':lab.LIMIT}
