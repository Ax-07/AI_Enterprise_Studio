"""Run the trusted protocol in the actual Docker isolation profile."""
import json
import verification as v
html="""<!doctype html><button id="run">Run</button><p id="out"></p>
<script>document.querySelector('#run').onclick=()=>{
 document.querySelector('#out').textContent='137.00';
}</script>"""
spec={'cases':[{'name':'Expected output','steps':[{'op':'click','selector':'#run'},{'op':'contains','selector':'#out','value':'137.00'}]},
               {'name':'Negative control','steps':[{'op':'click','selector':'#run'},{'op':'contains','selector':'#out','value':'99.00'}]}]}
r=v.run('fixture.html',html,json.dumps(spec),True)
print(json.dumps(r,ensure_ascii=False))
assert r['status']=='failed',r
assert [x['passed'] for x in r['checks']]==[True,False],r
print('Docker sandbox: positive and negative browser assertions observed')
