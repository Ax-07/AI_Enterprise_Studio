import json,unittest
from unittest.mock import patch
import test_autopilot,test_laboratory
import serveur as s,moteur as m,autopilot as a,portfolio as p,improvement as i,laboratory as l,verification as v
from laboratoire_fixture import HTML

# Synthetic candidate used by tests; not a delivered commercial product.
CANDIDATE=HTML.replace('<textarea id="data">','<input type="file" id="csv-file"><button id="import-csv" type="button">Importer</button><textarea id="data">').replace('</script>',"""
document.getElementById('import-csv').onclick=async()=>{
 const run=document.getElementById('run');run.disabled=true;
 try{
 const file=document.getElementById('csv-file').files[0];
 const lines=(await file.text()).trimEnd().split(/\\r?\\n/).slice(1);
 const rows=lines.map(line=>{const [sku,locale,title]=line.split(',');return {sku,locale,title}});
 document.getElementById('data').value=JSON.stringify({locales:['fr-FR','en-GB'],rows});
 }finally{run.disabled=false}
};
</script>""")

def mock_lab(row,*args):
    fixtures=l.catalogue(300,42)
    return {'profile':l.PROFILE,'revision':l.VERSION,'size':300,'seed':42,'sha256':l.digest(row['content']),
        'fixture_sha256':l.digest(l.encode(fixtures)),'fixtures':fixtures,'limit':l.LIMIT,'provenance':'LABORATOIRE_LOCAL',
        **l.score(fixtures,test_laboratory.observations())}

class ImprovementTests(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    product=test_laboratory.LabIntegration.product
    def prepared(self):
        pid,aid,other=self.product()
        with patch.object(l,'evaluate',side_effect=mock_lab):
            l.run(s,aid,l.PROFILE,300,42,self.cfg)
        return pid,aid
    def produce(self,cid,content,feature=True,regression=True,stop=False):
        actions=[self.act('delegate','NEXUS','Améliorer','Critère'),self.act('write_file','audit_catalogue.html',content,'Candidate'),
            self.act('finish',text='Nouvelle version'),self.act('finish',text='Conclusion')]
        def fake(url,headers,body=None):return self.reply(actions.pop(0))
        def verify(name,content,raw,enabled):
            status='failed' if content==HTML or not feature else 'passed'
            return {'status':status,'sha256':l.digest(content),'checks':[]}
        def bench(row,*args):
            r=mock_lab(row,*args)
            if not regression:r['metrics']['recall']=.96
            if stop:
                with s.db() as c:a.stop(c,cid)
            return r
        with patch.object(s,'config',return_value={**self.cfg,'html_sandbox_enabled':True}),patch.object(s,'request',side_effect=fake) as req,patch.object(l,'evaluate',side_effect=bench),patch.object(v,'run',side_effect=verify):
            a.worker(s,cid)
            self.assertEqual(req.call_count,4)
        self.assertEqual(actions,[])
    def test_auto_retain_and_restore(self):
        pid,aid=self.prepared()
        cid=self.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1)
        self.produce(cid,CANDIDATE)
        with s.db() as c:
            cy=i.cycle(c,cid);self.assertEqual(cy['state'],'retained')
            new=cy['candidate'];self.assertNotEqual(new,aid);self.assertEqual(p.latest(c,pid)['id'],new)
            self.assertEqual(i.row(c,aid)['content'],HTML)
            self.assertEqual(a.status(c)['state'],'terminé')
            self.assertEqual(len(a.status(c)['missions']),1)
            self.assertGreater(a.costs(c,cid),0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM laboratory_runs').fetchone()[0],2)
            i.restore(c,pid,aid)
            self.assertEqual(p.latest(c,pid)['id'],aid)
            self.assertEqual(i.row(c,new)['content'],CANDIDATE)
    def test_regression_reject_even_with_new_feature(self):
        pid,aid=self.prepared();cid=self.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1)
        self.produce(cid,CANDIDATE,regression=False)
        with s.db() as c:
            self.assertEqual(i.cycle(c,cid)['state'],'rejected')
            self.assertEqual(p.latest(c,pid)['id'],aid)
            self.assertIsNotNone(i.cycle(c,cid)['candidate'])
    def test_generic_review_and_manual_retain(self):
        pid,aid=self.prepared();cid=self.start(project=pid,improvement='generic',max_missions=1)
        self.produce(cid,CANDIDATE)
        with s.db() as c:
            cy=i.cycle(c,cid);self.assertEqual(cy['state'],'review')
            self.assertEqual(p.latest(c,pid)['id'],aid)
            i.retain_review(c,cy['id'])
            self.assertEqual(p.latest(c,pid)['id'],cy['candidate'])
    def test_stop_during_comparison_no_promotion(self):
        pid,aid=self.prepared();cid=self.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1)
        self.produce(cid,CANDIDATE,stop=True)
        with s.db() as c:
            self.assertEqual(i.cycle(c,cid)['state'],'pending')
            self.assertEqual(a.status(c)['state'],'arrêté')
            self.assertEqual(p.latest(c,pid)['id'],aid)
    def test_authorization_and_budget_before_network(self):
        pid,aid=self.prepared()
        for options in ({'max_missions':2},{'search_cap':1},{'permissions':dict.fromkeys(a.FLAGS,False)}):
            with self.assertRaises(ValueError):self.start(project=pid,improvement=i.CSV_PROFILE,**{'max_missions':1,**options})
        cid=self.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1,budget='0.01')
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=AssertionError('No network')) as req:
            a.worker(s,cid);req.assert_not_called()
        with s.db() as c:
            self.assertEqual(a.costs(c,cid),0)
            self.assertEqual(p.latest(c,pid)['id'],aid)
    def test_real_regression_csv_data(self):
        with s.db() as c:
            mid=m.create(s,c,'CSV','cloud')
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',1,'NEXUS','a,b\n1,2','test')",(mid,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,));p.sync(c)
            base=i.row(c,aid)
            spec=json.dumps({'checks':[{'op':'row_count','expected':1}]})
            r=v.run(base['name'],base['content'],spec)
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(aid,mid,spec,json.dumps(r)))
            frozen=i.plan(c,base,'generic')
            state,res=i.verify_pair(base,{'name':'kit.csv','content':'a,b\n1,2\n3,4'},frozen,'generic',self.cfg,None)
            self.assertEqual(state,'rejected')
            self.assertEqual(res['replays'][0]['result']['status'],'failed')
