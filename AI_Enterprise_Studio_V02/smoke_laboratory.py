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

# The new feature contract is executed against both baseline and a synthetic CSV-capable candidate.
from test_improvement import CANDIDATE
import improvement as i
base={'name':'audit_catalogue.html','content':HTML}
candidate={'name':'audit_catalogue.html','content':CANDIDATE}
baseline=l.evaluate(base,l.PROFILE,300,42,True)
state,comparison=i.verify_pair(base,candidate,{'replays':[],'lab':1},i.CSV_PROFILE,{'html_sandbox_enabled':True},baseline)
assert state=='retained',comparison.get('feature') or comparison.get('laboratory')
assert comparison['feature']['baseline']['status']=='failed'
assert comparison['feature']['candidate']['status']=='passed'
assert comparison['laboratory']['non_regression']
print('Docker amélioration: contrat CSV nouveau, banc catalogue non régressif, sélection technique')
