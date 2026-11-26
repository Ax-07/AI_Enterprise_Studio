const fs=require('fs'),assert=require('assert');
const req='a'.repeat(32);
for(const [kind,input,want] of [['health',{}, {ready:true}],['metrics',{values:[10,-3,7]},{count:3,sum:14,min:-3,max:10}]]){
 const w=JSON.parse(fs.readFileSync('n8n/aes_'+kind+'.json','utf8'));
 const node=new Function('$input','$execution',w.nodes[1].parameters.jsCode);
 const run=b=>node({first:()=>({json:{body:b}})},{id:17})[0].json;
 const body={protocol:'aes-n8n-v1',request_id:req,input};
 assert.deepStrictEqual(run(body),{protocol:'aes-n8n-v1',request_id:req,execution_id:'17',result:want});
 assert.throws(()=>run({...body,request_id:'wrong'}));
 assert.throws(()=>run({...body,extra:'x'}));
 assert.throws(()=>run({...body,input:{url:'https://example.org'}}));
 if(kind==='metrics'){
  assert.throws(()=>run({...body,input:{values:[true]}}));
  assert.throws(()=>run({...body,input:{values:[1.1]}}));
  assert.throws(()=>run({...body,input:{values:[100000001]}}));
  assert.throws(()=>run({...body,input:{values:[]}}));
 }
}
console.log('n8n code contracts: both workflows, positive and negative cases');

const cmp=JSON.parse(fs.readFileSync('n8n/aes_market_compare.json','utf8'));const runCmp=new Function('$input','$execution',cmp.nodes[1].parameters.jsCode);const b={protocol:'aes-n8n-v1',request_id:req,input:{rows:[{country:'FRA',population:1000,internet_bp:8000},{country:'GBR',population:900,internet_bp:9000}]}};assert.deepStrictEqual(runCmp({first:()=>({json:{body:b}})},{id:18})[0].json.result,{markets:[{country:'GBR',estimated_users:810},{country:'FRA',estimated_users:800}]});assert.throws(()=>runCmp({first:()=>({json:{body:{...b,input:{rows:[b.input.rows[0],b.input.rows[0]]}}}})},{id:18}));console.log('n8n market comparison contract OK');
