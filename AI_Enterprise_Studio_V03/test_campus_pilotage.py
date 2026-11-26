"""D04.3 against actual initialized schemas, no worker or external service."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools as tools

class CampusPilotageTests(unittest.TestCase):
    def test_native_read_projection(self):
        with tempfile.TemporaryDirectory() as d, patch.object(s,'DB',Path(d)/'db.sqlite3'), patch.object(s,'request',side_effect=AssertionError('External request forbidden')) as network:
            s.init()
            with s.db() as c:
                mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('Mission test','cloud','terminée')").lastrowid
                aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'test.txt',1,'NEXUS','private-file','test')",(mid,)).lastrowid
                cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('Campagne test',400000,3,'{}',2,'interrompu')").lastrowid
                c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'create')",(cid,mid))
                c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?,'test',1000,500,'mesuré','NEXUS')",(mid,))
                pid=c.execute("INSERT INTO enterprise_plans(budget,per_campaign,max_campaigns,search_cap,explore,state) VALUES(1000000,400000,2,4,0,'paused')").lastrowid
                c.execute("INSERT INTO enterprise_plan_queue(plan,kind,reason,campaign) VALUES(?,'project','test',?)",(pid,cid))
                gid=c.execute("INSERT INTO periodic_grants(cadence,seconds,periods,starts,expires,last_seen,total_budget,period_budget,per_campaign,max_campaigns,total_search,period_search,explore,state) VALUES('daily',86400,2,1,172801,1,2000000,1000000,400000,2,4,2,0,'suspended')").lastrowid
                c.execute("INSERT INTO periodic_slots(grant_id,slot,starts,expires,plan) VALUES(?,1,1,86401,?)",(gid,pid))
                project=c.execute("INSERT INTO projects(origin,title,state) VALUES('test-proj','Projet test','active')").lastrowid
                c.execute("INSERT INTO project_missions(mission,project,provenance) VALUES(?,?,'test')",(mid,project))
                c.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,'test',1,10,1,'hash','failed','private-result')",(aid,))
                c.execute("INSERT INTO rewards(mission,agent,xp,reason) VALUES(?,'NEXUS',7,'test')",(mid,))
                cap=next(iter(s.connectors.REGISTRY))
                c.execute("INSERT INTO connector_runs(capability,actor,input_sha256,reserved,state,diagnostic) VALUES(?,'ORION','hash',0,'unknown','private-diagnostic')",(cap,))
            before=s.DB.read_bytes()
            def read(name):
                return tools.read(s.DB,name,{},roles=s.moteur.ROLES,permissions=s.moteur.PERMS,registry=s.connectors.REGISTRY)['rows']
            home=read('home')
            self.assertEqual([x['kind'] for x in home],['campaign','plan','periodic'])
            self.assertEqual(home[0]['committed'],500)
            self.assertEqual(home[1]['committed'],500)
            self.assertEqual(home[2]['slots'],1)
            self.assertEqual(read('portfolio')[0]['artifacts'],1)
            self.assertEqual(read('laboratory')[0]['status'],'failed')
            self.assertNotIn('result',read('laboratory')[0])
            caps=read('tools')
            self.assertTrue(any(x['kind']=='run' and x['state']=='unknown' for x in caps))
            self.assertTrue(all('secret_env' not in x and 'diagnostic' not in x for x in caps))
            self.assertEqual(len(read('agents')),8)
            nexus=next(x for x in read('goals') if x['id']=='NEXUS')
            self.assertEqual(nexus['xp'],7)
            self.assertEqual(s.DB.read_bytes(),before)
            network.assert_not_called()
