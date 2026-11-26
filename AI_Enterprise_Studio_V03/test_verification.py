import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import verification as v
import serveur as s
import moteur as m

class DataTests(unittest.TestCase):
    def run_spec(self,name,content,spec):
        return v.run(name,content,json.dumps(spec))
    def test_csv_assertions(self):
        data='Payout ID,Net,Currency\nA,97.00,EUR\nA,-20.00,EUR\nB,49.00,EUR\n'
        checks=[{'op':'sum','column':'Net','where':{'Payout ID':'A'},'expected':'77.00'},
                {'op':'row_count','where':{'Payout ID':'A'},'expected':2},
                {'op':'cell','column':'Net','row':0,'expected':'97.00'},
                {'op':'unique','column':'Payout ID','expected':False}]
        r=self.run_spec('kit.csv',data,{'checks':checks})
        self.assertEqual(r['status'],'passed')
        self.assertEqual(r['sha256'],hashlib.sha256(data.encode()).hexdigest())
        checks[0]['expected']='76.99'
        self.assertEqual(self.run_spec('kit.csv',data,{'checks':checks})['status'],'failed')
    def test_csv_invalid(self):
        for data in ('a,a\n1,2','a,b\n1','a,b\n"1,2'):
            self.assertEqual(self.run_spec('x.csv',data,{'checks':[{'op':'row_count','expected':1}]})['status'],'invalid')
    def test_json_checks(self):
        data='{"items":[{"ok":true},{"ok":false}]}'
        spec={'checks':[{'op':'length','path':['items'],'expected':2},{'op':'equals','path':['items',1,'ok'],'expected':False}]}
        self.assertEqual(self.run_spec('x.json',data,spec)['status'],'passed')
        spec['checks'][1]['expected']=0
        self.assertEqual(self.run_spec('x.json',data,spec)['status'],'failed')
        for data in ('{"a":1,"a":2}','{"a":NaN}','{"a":1e999}'):
            self.assertEqual(self.run_spec('x.json',data,spec)['status'],'invalid')
    def test_html_disabled_no_process(self):
        with patch.object(v,'browser_results') as browser:
            r=self.run_spec('x.html','<p>hello</p>',{'cases':[{'name':'A','steps':[{'op':'contains','selector':'p','value':'hello'}]}]})
            self.assertEqual(r['status'],'unavailable')
            browser.assert_not_called()
    def test_html_protocol_and_limits(self):
        for steps in ([{'op':'evaluate','selector':'p','value':'1'}],[{'op':'click','selector':'p'}],[{'op':'contains','selector':'p >> text=x','value':'x'}]):
            self.assertEqual(self.run_spec('x.html','<p>hello</p>',{'cases':[{'name':'A','steps':steps}]})['status'],'invalid')
        self.assertEqual(self.run_spec('x.py','print(1)',{})['status'],'unavailable')
        self.assertEqual(self.run_spec('x.html','a'*24001,{'cases':[]})['status'],'invalid')
    def test_html_report_and_docker_arguments(self):
        spec={'cases':[{'name':'A','steps':[{'op':'contains','selector':'p','value':'hello'}]}]}
        with patch.object(v,'browser_results',return_value=[{'name':'A','passed':False,'step':1}]) as browser:
            r=v.run('x.html','<p>hello</p>',json.dumps(spec),True)
            self.assertEqual(r['status'],'failed');browser.assert_called_once()
        base,args=v.docker_command('dummy','aes-test-fake')
        for flag in ('--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user=1000:1000','--pull=never','--pids-limit=128'):
            self.assertIn(flag,args)
        self.assertNotIn('--privileged',args);self.assertNotIn('-v',args);self.assertNotIn('--mount',args)
    def test_shopify_contract(self):
        self.assertEqual(len(v.html_spec(v.shopify_spec())),4)

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=patch.object(s,'DB',Path(self.tmp.name)/'db');p.start();self.addCleanup(p.stop)
        s.init();self.cfg=s.config()
        with s.db() as c:
            self.source=m.create(s,c,'Source','cloud')
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',1,'NEXUS','a,b\n1,2\n','test')",(self.source,)).lastrowid
            self.html=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'prototype_rapprochement_shopify_fr_en.html',1,'NEXUS','<p>prototype</p>','test')",(self.source,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(self.source,))
            self.mid=m.create(s,c,'Test','cloud',self.aid)
    def act(self,agent,target):
        with s.db() as c:
            tid=m.add_task(c,self.mid,agent,'test')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
        return m.execute(s,t,{'action':'test_file','target':target,'text':json.dumps({'checks':[{'op':'sum','column':'b','expected':'2'}]}),'detail':''},self.cfg,'cloud')
    def test_reference_persistence_and_permission(self):
        with patch.object(s,'request',side_effect=AssertionError('No network')) as net:
            result=self.act('SENTINEL','ref:'+str(self.aid))
            self.assertEqual(result['status'],'passed')
            with self.assertRaises(ValueError):self.act('ORION','ref:'+str(self.aid))
            with self.assertRaises(ValueError):self.act('NEXUS','ref:'+str(self.html))
            net.assert_not_called()
        with s.db() as c:
            rows=list(c.execute('SELECT * FROM verification_results'))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['artifact'],self.aid)
            self.assertEqual(rows[0]['mission'],self.mid)
            self.assertEqual(json.loads(rows[0]['result'])['status'],'passed')
            self.assertEqual(m.extra_status(s,c)['verifications'][0]['agent'],'SENTINEL')
            self.assertEqual(s.used(c),0)
    def test_quick_unavailable(self):
        with patch.object(v,'browser_results') as browser:
            r=m.quick_verify(s,self.html,{**self.cfg,'html_sandbox_enabled':False})
            self.assertEqual(r['status'],'unavailable');browser.assert_not_called()
        with self.assertRaises(ValueError):m.quick_verify(s,self.aid,self.cfg)
    def test_migration_idempotent(self):
        m.quick_verify(s,self.html,{**self.cfg,'html_sandbox_enabled':False})
        s.init()
        with s.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM verification_results').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],2)
