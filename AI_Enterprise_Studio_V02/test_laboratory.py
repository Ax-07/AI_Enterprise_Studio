import json,unittest
from unittest.mock import patch
import laboratoire_fixture as fixture
import laboratory as l,verification as v,serveur as s,moteur as m,autopilot as a,portfolio as p
import test_autopilot

def observations(size=300,seed=42):
    result=[]
    for f in l.catalogue(size,seed):
        out=f.get('expected_error') if 'expected_error' in f else '\n'.join(f['expected']+[f['total']])
        result.append({'name':f['name'],'passed':True,'output':out,'elapsed_ms':25})
    return result

class LabTests(unittest.TestCase):
    def test_seed_and_injection(self):
        x=l.catalogue(300,42)
        self.assertEqual(x,l.catalogue(300,42))
        self.assertNotEqual(x,l.catalogue(300,43))
        self.assertEqual(len(json.loads(x[1]['input'])['rows']),300)
        self.assertEqual(len(x[1]['expected']),42)
        self.assertEqual(x[1]['total'],'TOTAL | P1 30 | P2 12')
        self.assertEqual(l.score(x,observations())['metrics']['recall'],1)
        self.assertEqual(l.score(x,observations())['metrics']['false_alert_share'],0)
    def test_false_alert_missing_and_unavailable(self):
        x=l.catalogue(300,42);o=observations()
        lines=o[1]['output'].splitlines()
        lines[0]='P1 | anomalie inattendue'
        o[1]['output']='\n'.join(lines)
        r=l.score(x,o)
        self.assertEqual((r['metrics']['tp'],r['metrics']['fp'],r['metrics']['fn']),(41,1,1))
        # Larger errors and wrong totals are not a success.
        o[1]['output']='TOTAL | P1 0 | P2 0'
        self.assertEqual(l.score(x,o)['status'],'failed')
        o[2]['passed']=False
        self.assertIsNone(l.score(x,o)['metrics'])
        self.assertEqual(l.score(x,o)['status'],'unavailable')
    def test_no_oracle_in_browser_payload(self):
        with patch.object(v,'browser_results',return_value=observations()) as runner:
            r=l.evaluate({'name':'audit_catalogue.html','content':fixture.HTML},l.PROFILE,300,42,True)
        self.assertEqual(r['status'],'passed')
        args,kw=runner.call_args
        self.assertTrue(all(set(x)=={'name','input'} for x in args[1]))
        self.assertEqual(kw,{'image':l.IMAGE,'mode':'laboratory'})
        self.assertEqual(r['sha256'],l.digest(fixture.HTML))
        self.assertEqual(r['fixture_sha256'],l.digest(l.encode(r['fixtures'])))
    def test_disabled_and_bad_type(self):
        with patch.object(v,'browser_results') as runner:
            self.assertEqual(l.evaluate({'name':'audit_catalogue.html','content':'<p>x</p>'},l.PROFILE,300,42,False)['status'],'unavailable')
            runner.assert_not_called()
        with self.assertRaises(ValueError):l.evaluate({'name':'cases.json','content':'{}'},l.PROFILE,300,42,True)
        with self.assertRaises(ValueError):l.catalogue(True,42)
        with self.assertRaises(ValueError):l.catalogue(300,-1)

class LabIntegration(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    def product(self):
        with s.db() as c:
            mid=m.create(s,c,'Catalogue','cloud')
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'audit_catalogue.html',1,'NEXUS',?,'moteur')",(mid,fixture.HTML)).lastrowid
            other=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'cas_audit_catalogue.json',1,'NEXUS','{}','cas')",(mid,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,));p.sync(c)
            pid=c.execute('SELECT project FROM project_missions WHERE mission=?',(mid,)).fetchone()[0]
            self.assertEqual(p.latest(c,pid)['id'],aid)
            return pid,aid,other
    def test_auto_local_then_stops_at_failure(self):
        pid,aid,other=self.product()
        cid=self.start(project=pid)
        with s.db() as c:self.assertEqual(a.choose(c,a._campaign(c,cid))[0],('laboratory',aid,None))
        obs=observations();obs[1]['output']='TOTAL | P1 0 | P2 0'
        with patch.object(s,'config',return_value={**self.cfg,'html_sandbox_enabled':True}),patch.object(v,'browser_results',return_value=obs) as browser,patch.object(s,'request',side_effect=AssertionError('No provider')) as req:
            a.worker(s,cid);browser.assert_called_once();req.assert_not_called()
        with s.db() as c:
            st=a.status(c,self.cfg)
            self.assertEqual(st['state'],'terminé');self.assertEqual(st['spent'],0)
            self.assertEqual(st['missions'],[])
            self.assertEqual(st['laboratory'][0]['status'],'failed')
            self.assertIsNone(p.next_step(c,pid,dict.fromkeys(a.FLAGS,True))[0])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM verification_results').fetchone()[0],0)
    def test_pass_then_real_html_audit_not_fixture(self):
        pid,aid,other=self.product()
        cid=self.start(project=pid,permissions={'research':False,'production':False,'tests':True,'market':False},max_missions=1)
        actions=[self.act('delegate','SENTINEL','Audit','Critère'),self.act('finish',text='Pas de preuve agent'),self.act('finish',text='Conclusion partielle')]
        def fake(url,headers,body=None):return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value={**self.cfg,'html_sandbox_enabled':True}),patch.object(v,'browser_results',return_value=observations()) as browser,patch.object(s,'request',side_effect=fake) as req:
            a.worker(s,cid);browser.assert_called_once();self.assertEqual(req.call_count,3)
        with s.db() as c:
            st=a.status(c,self.cfg)
            self.assertEqual(st['laboratory'][0]['status'],'passed')
            self.assertEqual(st['missions'][0]['artifact'],aid)
            self.assertEqual(st['missions'][0]['kind'],'functional')
            self.assertEqual(p.status(c)['projects'][0]['laboratory']['artifact'],aid)
            self.assertIsNone(p.next_step(c,pid,dict.fromkeys(a.FLAGS,True))[0])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM verification_results').fetchone()[0],0)
    def test_exact_hash_and_not_json(self):
        pid,aid,other=self.product()
        with patch.object(v,'browser_results',return_value=observations()):
            r=l.run(s,aid,l.PROFILE,300,42,{**self.cfg,'html_sandbox_enabled':True})
        with self.assertRaises(ValueError):l.run(s,other,l.PROFILE,300,42,self.cfg)
        with s.db() as c:
            self.assertEqual(l.canonical(c,p.latest(c,pid))['id'],r['id'])
            c.execute("UPDATE artifacts SET content=content||' ' WHERE id=?",(aid,))
            self.assertIsNone(l.canonical(c,p.latest(c,pid)))
