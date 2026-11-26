import json, os, unittest
from unittest.mock import patch, MagicMock
import serveur as s, moteur as m, autopilot as a, connectors as x
import intelligence as i, n8n_bridge as n, collective_evidence as e
import test_intelligence as ti
from test_autopilot import AutopilotTests

class CollectiveEvidenceTests(unittest.TestCase):
    setUp=AutopilotTests.setUp
    start=AutopilotTests.start
    policy=ti.IntelligenceTests.policy

    def test_historical_campaign_detects_omissions_and_false_negatives_without_network(self):
        with patch.dict(os.environ,{'AES_N8N_TOKEN':ti.TOKEN}):
            self.policy(i.CAP);self.policy(n.COMPARE)
            cid=self.start(project='explore',connector_cap=2,max_missions=1)
            with s.db() as c:
                mid=m.create(s,c,'Recherche','cloud')
                c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
                tid=m.add_task(c,mid,'ORION','Recherche')
                midas=m.add_task(c,mid,'MIDAS','Évaluation')
                for name in ('Catalogue','Sous-titres'):
                    c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,'Hypothèse','Test')",(mid,name))
                oid=c.execute('SELECT MIN(id) FROM opportunities WHERE mission=?',(mid,)).fetchone()[0]
            with patch.dict(x.ADAPTERS,{i.CAP:MagicMock(side_effect=ti.fixture)}):
                source=x.invoke(s,i.CAP,ti.SPEC,mid,tid,'ORION')
            def bridge(cap,value,rid):
                return {'request_id':rid,'execution_id':'134','result':n.expected(cap,value),'protocol':n.PROTOCOL}
            with patch.object(n,'call',side_effect=bridge):
                compare=x.invoke(s,n.COMPARE,json.dumps({'source_run':source['run']}),mid,tid,'ORION')
            with s.db() as c:
                assumptions={'price_cents':10000,'variable_cost_cents':4500,'fixed_month_cents':11000,
                    'monthly_units':10,'automation_pct':80,'risk':4,'source_runs':[],'rationale':'Hypothèses non certifiées, coûts à vérifier.'}
                i.assess(c,mid,'MIDAS',str(oid),json.dumps(assumptions))
                for step,(agent,report) in enumerate([('MIDAS',"Le relevé est macroéconomique ; `n8n.market_compare` n’a pas été appelé."),('ATLAS',"Aucun résultat n8n n’est attesté.")]):
                    c.execute("INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,?,?,?,?)",
                        (mid,step,agent,json.dumps({'rapport':report}),'[]'))
                c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
                c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            with patch.object(s,'request',side_effect=AssertionError('External forbidden')) as network,patch.object(n,'call',side_effect=AssertionError('External forbidden')):
                with s.db() as c:
                    changes=c.total_changes
                    facts=e.registry(c,mid)
                    self.assertEqual(facts['connector_count'],2)
                    self.assertEqual(facts['opportunity_count'],2)
                    self.assertEqual(facts['assessed_count'],1)
                    self.assertEqual(facts['connectors'][1]['execution_id'],'134')
                    self.assertEqual(facts['connectors'][1]['source_run'],source['run'])
                    self.assertEqual([v['code'] for v in facts['findings']],
                        ['opportunity_unassessed','possible_n8n_report_contradiction','possible_n8n_report_contradiction'])
                    self.assertEqual(facts['sentinel_tasks'],[])
                    self.assertNotIn(ti.TOKEN,json.dumps(facts))
                    export=s.campaign_audit(c,self.cfg,cid)
                    self.assertEqual(export['missions'][0]['collective_evidence'],facts)
                    self.assertTrue(export['collective_audit']['review_required'])
                    self.assertEqual(c.total_changes,changes)
                network.assert_not_called()
            with s.db() as c:
                c.execute("UPDATE connector_workflow_results SET result=replace(result,'134','135') WHERE run=?",(compare['run'],))
                facts=e.registry(c,mid)
                self.assertFalse(facts['connectors'][1]['integrity'])
                self.assertEqual(facts['findings'][0]['code'],'connector_integrity')
                self.assertFalse(any(v['code']=='possible_n8n_report_contradiction' for v in facts['findings']))
                c.execute("UPDATE opportunities SET body='modifié' WHERE id=?",(oid,))
                self.assertEqual(e.registry(c,mid)['assessed_count'],0)
                other=m.create(s,c,'Autre mission','cloud')
                self.assertEqual(e.registry(c,other)['connector_count'],0)

    def test_sentinel_only_when_tests_authorized(self):
        cid=self.start(permissions={'research':True,'production':False,'tests':False,'market':False})
        with s.db() as c:
            mid=m.create(s,c,'Recherche','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'opportunity')",(cid,mid))
            with self.assertRaises(ValueError):a.guard(c,mid,'ATLAS','delegate','SENTINEL',{'delegate'})
            c.execute("UPDATE campaigns SET permissions=? WHERE id=?",(json.dumps(dict.fromkeys(a.FLAGS,True)),cid))
            a.guard(c,mid,'ATLAS','delegate','SENTINEL',{'delegate'})
            with self.assertRaises(ValueError):a.guard(c,mid,'ATLAS','delegate','NEXUS',{'delegate'})
