"""Run the reconstructed user-provided algorithm inside real Docker isolation."""
import json
import laboratory as l
from laboratoire_fixture import HTML
for size in l.SIZES:
    r=l.evaluate({'name':'audit_catalogue.html','content':HTML},l.PROFILE,size,42,True)
    assert r['status']=='passed',r.get('error') or r.get('metrics') or r['cases']
    assert r['metrics']['tp']==size*14//100 and r['metrics']['fp']==r['metrics']['fn']==0,r['metrics']
    print('Docker laboratoire:',size,'lignes',json.dumps(r['metrics']), 'temps', [x['elapsed_ms'] for x in r['cases']])
bad=HTML.replace('...required,...duplicates,...missing,','')
r=l.evaluate({'name':'audit_catalogue.html','content':bad},l.PROFILE,300,42,True)
assert r['status']=='failed' and r['metrics']['fn']==42,r.get('metrics')
print('Docker laboratoire: contrôle négatif détecté')
