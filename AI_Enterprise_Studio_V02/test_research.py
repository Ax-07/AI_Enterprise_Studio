import json,ssl,unittest
from unittest.mock import patch
import serveur as s,moteur as m,autopilot as a,portfolio as p,intelligence as i,research as r
from test_autopilot import AutopilotTests
from test_portfolio import PortfolioTests

class ResearchTests(unittest.TestCase):
    setUp=AutopilotTests.setUp
    start=AutopilotTests.start
    historical=PortfolioTests.historical

    def test_fixed_diagnostic_with_certificate_and_http_errors(self):
        def fetch(url):
            if url==r.PROBES[1][1]:raise ssl.SSLCertVerificationError('unable to get local issuer certificate')
            if url==r.PROBES[2][1]:raise ValueError('HTTP 202 (non exploitable)')
            return {'texte':'Page exemple','partiel':False}
        with patch.object(s,'request',side_effect=AssertionError('Paid call forbidden')) as net:
            d=r.diagnostic(fetch)
            self.assertTrue(d['verify_required']);self.assertTrue(d['hostname_check'])
            self.assertEqual([x['state'] for x in d['checks']],['received','failed','failed'])
            self.assertEqual([x.get('code') for x in d['checks']],[None,'tls_certificate','http_202'])
            self.assertEqual([x['url'] for x in d['checks']],[v for _,v in r.PROBES])
            net.assert_not_called()
        with s.db() as c:self.assertEqual(s.used(c),0)

    def test_failed_url_not_repeated_and_alternative_is_available(self):
        with s.db() as c:
            mid=m.create(s,c,'Étude','cloud')
            tid=m.add_task(c,mid,'ORION','Recherche')
            task=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            c.execute("INSERT INTO searches(mission,query,status,result) VALUES(?,'test','reçue',?)",(mid,json.dumps([{'url':'https://a.example/'},{'url':'https://b.example/'}])))
        def action(url):return {'action':'read','target':url,'text':'','detail':''}
        with patch.object(m,'fetch_page',side_effect=[ssl.SSLCertVerificationError('issuer absent'),{'url':'https://b.example/','texte':'Texte public','partiel':False}]) as fetch:
            with self.assertRaisesRegex(ValueError,'tls_certificate'):m.execute(s,task,action('https://a.example/'),self.cfg,'cloud')
            with self.assertRaisesRegex(ValueError,'déjà échouée'):m.execute(s,task,action('https://a.example/'),self.cfg,'cloud')
            with self.assertRaisesRegex(ValueError,'non issue'):m.execute(s,task,action('https://c.example/'),self.cfg,'cloud')
            result=m.execute(s,task,action('https://b.example/'),self.cfg,'cloud')
            self.assertIn('page_ref',result);self.assertEqual(fetch.call_count,2)
        with s.db() as c:
            report=r.mission(c,mid,full=True)
            self.assertEqual(report['searches_received'],1)
            self.assertEqual(report['pages_received'],1)
            self.assertEqual(report['pages'][0]['failure']['code'],'tls_certificate')
            self.assertEqual(report['pages'][1]['excerpt'],'Texte public')

    def test_explicit_mode_and_economic_hold(self):
        *_,opp,old,new=self.historical()
        flags=dict.fromkeys(a.FLAGS,True)
        with s.db() as c:
            mid=c.execute('SELECT mission FROM opportunities WHERE id=?',(opp,)).fetchone()[0]
            d={'price_cents':2500,'variable_cost_cents':1000,'fixed_month_cents':12000,'monthly_units':5,'automation_pct':80,'risk':4,'source_runs':[],'rationale':'Hypothèses non vérifiées de coûts et de prix.'}
            i.assess(c,mid,'MIDAS',str(opp),json.dumps(d))
            self.assertTrue(p.economic_hold(c,opp))
            step,reason=p.next_step(c,new,flags)
            self.assertIsNone(step);self.assertIn('Production suspendue',reason)
            self.assertNotEqual(p.recommend(c,flags)['id'],new)
        with self.assertRaises(ValueError):self.start(project='explore',campaign_mode='commercial',max_missions=1)
        with self.assertRaises(ValueError):self.start(project='explore',campaign_mode='progression')
        with self.assertRaises(ValueError):self.start(project=new,campaign_mode='progression')
        flags['production']=False
        cid=self.start(project=new,campaign_mode='commercial',commercial=True,permissions=flags,max_missions=1)
        with s.db() as c:
            self.assertEqual(p.scope(c,cid)['scope'],'commercial')
            self.assertEqual(a.choose(c,a._campaign(c,cid))[0][0],'commercial')
            # New positive assessment permits production, but remains a hypothesis.
            d['monthly_units']=10
            i.assess(c,mid,'MIDAS',str(opp),json.dumps(d))
            self.assertFalse(p.economic_hold(c,opp))
            self.assertEqual(p.next_step(c,new,dict.fromkeys(a.FLAGS,True))[0][0],'create')
