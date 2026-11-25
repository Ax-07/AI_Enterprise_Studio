import json,os,unittest
from unittest.mock import patch,MagicMock
import serveur as s,moteur as m,autopilot as a,connectors as x,n8n_bridge as n,intelligence as i
import test_autopilot

TOKEN='T'*43
SPEC='{"countries":["GBR","FRA"],"year":2023}'
def fixture(value=SPEC,missing=False):
    d=i.decode(i.request_spec(value));rows=[]
    for country in d['countries']:
        vals=(1000,80,10000) if country=='FRA' else (900,90,20000)
        for key,v in zip(i.INDICATORS,vals):
            rows.append({'countryiso3code':country,'indicator':{'id':key},'date':str(d['year']),'value':None if missing and country=='GBR' and key=='IT.NET.USER.ZS' else v})
    raw=json.dumps([{'page':1,'pages':1,'total':len(rows),'lastupdated':'2025-10-01'},rows]).encode()
    snap=i.parse(raw,d)
    return {'source':'World Bank / WDI (source 2)','url':i.url_for(d),'retrieved':'2026-11-25T00:00:00+00:00','raw_sha256':__import__('hashlib').sha256(raw).hexdigest(),'snapshot':snap,'snapshot_sha256':i.digest(snap),'raw_json':raw.decode('utf8')}

class IntelligenceTests(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    def policy(self,cap):
        with s.db() as c:x.set_policy(c,{'capability':cap,'enabled':True,'agents':['ORION','MIDAS'],'max_calls':20,'budget':'0'})
    def test_request_and_parse(self):
        d=i.decode(i.request_spec(SPEC));self.assertEqual(d['countries'],['FRA','GBR'])
        self.assertIn('/country/FRA;GBR/indicator/',i.url_for(d))
        for val in ('{"countries":["FRA","FRA"],"year":2023}','{"countries":["FRA","USA/"],"year":2023}','{"countries":["FRA","GBR"],"year":true}','{"countries":["FRA","GBR"],"year":2099}','{"countries":["FRA","GBR"],"year":2023,"url":"http://x"}'):
            with self.assertRaises(ValueError):i.request_spec(val)
        f=fixture();self.assertEqual(len(f['snapshot']['observations']),6)
        self.assertFalse(i.comparable(fixture(missing=True)['snapshot']))
        row={'countryiso3code':'FRA','indicator':{'id':'IT.NET.USER.ZS'},'date':'2023','value':101}
        for r in ([row],[{**row,'value':90},{**row,'value':90}],[{**row,'date':'2024','value':90}]):
            with self.assertRaises(ValueError):i.parse(json.dumps([{'page':1,'pages':1,'total':len(r)},r]).encode(),d)
        with self.assertRaises(ValueError):i.parse(b' '*65537,d)
    def test_transport_fixed_origin_and_no_credentials(self):
        d=i.decode(i.request_spec(SPEC));row={'countryiso3code':'FRA','indicator':{'id':'IT.NET.USER.ZS'},'date':'2023','value':90}
        with patch.object(i.http.client,'HTTPSConnection') as conn:
            r=MagicMock(status=200);conn.return_value.getresponse.return_value=r
            r.read.return_value=json.dumps([{'page':1,'pages':1,'total':1},[row]]).encode()
            f=i.fetch(SPEC);self.assertEqual(f['snapshot']['observations'][1]['value'],90)
            self.assertEqual(conn.call_args.args,('api.worldbank.org',443))
            self.assertEqual(conn.return_value.request.call_args.args[0],'GET')
            self.assertNotIn('Authorization',conn.return_value.request.call_args.kwargs['headers'])
            r.status=302
            with self.assertRaises(RuntimeError):i.fetch(SPEC)
            self.assertEqual(conn.call_count,2)
    def test_agent_pipeline_and_ranking_real_engine(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}):
            self.policy(i.CAP);self.policy(n.COMPARE)
            cid=self.start(project='explore',connector_cap=2,max_missions=1)
            assumptions={'price_cents':4900,'variable_cost_cents':2500,'fixed_month_cents':10000,'monthly_units':10,'automation_pct':80,'risk':3,'source_runs':[1],'rationale':'Hypothèses incluant tous les coûts variables; pas de demande démontrée.'}
            bad={**assumptions,'price_cents':2000}
            actions=[self.act('delegate','ORION','Comparer les marchés','Relevé puis opportunités'),self.act('connector',i.CAP,SPEC),
                     self.act('connector',n.COMPARE,'{"source_run":1}'),self.act('opportunity','Kit numérique','Hypothèse secteur A','Test de demande'),self.act('opportunity','Service B2B','Hypothèse secteur B','Test de demande'),self.act('finish',text='Sources macro et hypothèses'),
                     self.act('delegate','MIDAS','Évaluer les deux pistes','Scénarios'),self.act('assess_opportunity','1',json.dumps(assumptions)),self.act('assess_opportunity','2',json.dumps(bad)),self.act('finish',text='Évaluations hypothétiques'),self.act('finish',text='Classement sans décision commerciale')]
            def fake(url,headers,body=None):
                action=actions.pop(0);self.assertIn(action['action'],body['text']['format']['schema']['properties']['action']['enum'])
                self.assertNotIn(TOKEN,json.dumps(body))
                if action['action']=='assess_opportunity':self.assertIn('SOURCES MACRO OFFICIELLES REÇUES',body['input'])
                return self.reply(action)
            def bridge(cap,value,rid):
                self.assertEqual(cap,n.COMPARE)
                self.assertEqual(json.loads(value),{'rows':[{'country':'FRA','population':1000,'internet_bp':8000},{'country':'GBR','population':900,'internet_bp':9000}]})
                return {'request_id':rid,'execution_id':'22','result':n.expected(cap,value),'protocol':n.PROTOCOL}
            with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake),patch.dict(x.ADAPTERS,{i.CAP:MagicMock(side_effect=fixture)}) as adapters,patch.object(n,'call',side_effect=bridge) as call:
                a.worker(s,cid)
                adapters[i.CAP].assert_called_once();call.assert_called_once()
            self.assertEqual(actions,[])
            with s.db() as c:
                st=a.status(c);self.assertEqual(st['state'],'terminé',st);self.assertEqual(st['connectors']['calls'],2)
                v=i.status(c);self.assertEqual(len(v['ranking']),2)
                good=v['ranking'][0]['result'];self.assertEqual(good['contribution_cents'],2400);self.assertEqual(good['monthly_result_cents'],14000);self.assertEqual(good['breakeven_units'],5)
                self.assertGreater(good['score'],0);self.assertEqual(v['ranking'][1]['result']['score'],0)
                self.assertTrue(v['sources'][0]['integrity']);self.assertEqual(v['comparisons'][0]['result']['source_run'],1)
                self.assertEqual(v['comparisons'][0]['result']['result']['markets'][0]['country'],'GBR')
                self.assertNotIn(TOKEN,json.dumps(v))
                c.execute("UPDATE opportunities SET body='Modifié' WHERE id=1")
                self.assertEqual(len(i.ranking(c)),1)
    def test_cross_mission_refs_and_owner_test_separation(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}):
            self.policy(i.CAP);self.policy(n.COMPARE)
            with patch.dict(x.ADAPTERS,{i.CAP:MagicMock(side_effect=fixture)}):
                self.assertEqual(x.invoke(s,i.CAP,SPEC)['status'],'received')
            cid=self.start(project='explore',connector_cap=2)
            with s.db() as c:
                mid=m.create(s,c,'Recherche','cloud');c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
                tid=m.add_task(c,mid,'ORION','Recherche');o=c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,'Piste','Hypothèse','Test')",(mid,)).lastrowid
            with patch.object(n,'call') as call:
                with self.assertRaises(ValueError):x.invoke(s,n.COMPARE,'{"source_run":1}',mid,tid,'ORION')
                call.assert_not_called()
            with s.db() as c:
                self.assertEqual(x.campaign_status(c,cid)['calls'],0)
                with self.assertRaises(ValueError):i.assess(c,mid,'ORION',str(o),'{}')
                with self.assertRaises(ValueError):i.source(c,1,mid)
    def test_integrity_and_duplicate_source(self):
        self.policy(i.CAP);cid=self.start(project='explore',connector_cap=2)
        with s.db() as c:
            mid=m.create(s,c,'Recherche','cloud');c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid));tid=m.add_task(c,mid,'ORION','Recherche')
        with patch.dict(x.ADAPTERS,{i.CAP:MagicMock(side_effect=fixture)}) as adapters:
            self.assertEqual(x.invoke(s,i.CAP,SPEC,mid,tid,'ORION')['status'],'received')
            with self.assertRaises(ValueError):x.invoke(s,i.CAP,'{"year":2023,"countries":["FRA","GBR"]}',mid,tid,'ORION')
            adapters[i.CAP].assert_called_once()
        with s.db() as c:
            c.execute("UPDATE market_sources SET snapshot='{}' WHERE run=1")
            with self.assertRaises(ValueError):i.source(c,1,mid)
            self.assertFalse(i.status(c)['sources'][0]['integrity'])
