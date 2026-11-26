import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools,improvement,verification,laboratory

class CampusImprovementTests(unittest.TestCase):
    def test_history_is_read_only_and_bounded(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            s.init()
            with s.db() as c:
                # Schema fixture: no real cycle executed or provider called.
                mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('Fixture','cloud','terminée')").lastrowid
                oid=c.execute("INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,'Fixture','fixture','test')",(mid,)).lastrowid
                pid=c.execute("INSERT INTO projects(origin,title,opportunity) VALUES('fixture:improvement','Fixture',?)",(oid,)).lastrowid
                cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('Fixture',100000,1,'{}',0,'terminé')").lastrowid
                ids=[]
                for version,content in [(1,'a,b\\n1,2'),(2,'a,b\\n1,3')]:
                    aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',?,'NEXUS',?,'fixture')",(mid,version,content)).lastrowid
                    ids.append((aid,hashlib.sha256(content.encode()).hexdigest()))
                (base,bsha),(candidate,csha)=ids
                c.execute("INSERT INTO product_references(project,artifact,sha256) VALUES(?,?,?)",(pid,base,bsha))
                payload={'replays':[{'proof':1,'result':{'status':'passed','secret':'PRIVATE_PAYLOAD'}}],'laboratory':{'non_regression':True},'feature':{'baseline':{'status':'failed'},'candidate':{'status':'passed'}}}
                c.execute("""INSERT INTO improvement_cycles(campaign,project,baseline,baseline_sha,candidate,candidate_sha,profile,goal,plan,state,result)
                    VALUES(?,?,?,?,?,?,'generic','PRIVATE_GOAL','{}','review',?)""",(cid,pid,base,bsha,candidate,csha,json.dumps(payload)))
            before=s.DB.read_bytes()
            with patch.object(s,'request',side_effect=AssertionError('No provider')) as net,patch.object(verification,'run',side_effect=AssertionError('No test')),patch.object(laboratory,'evaluate',side_effect=AssertionError('No lab')),patch.object(improvement,'complete',side_effect=AssertionError('No cycle')):
                result=campus_tools.read(s.DB,'improvements',{})
                net.assert_not_called()
            summary,row=result['rows']
            self.assertFalse(summary['training_performed'])
            self.assertEqual(summary['counts'],[{'state':'review','count':1}])
            self.assertEqual(row['reference'],base)
            self.assertEqual(row['candidate_identity'],'match')
            self.assertEqual(row['replays'],[{'proof':1,'status':'passed'}])
            self.assertTrue(row['non_regression'])
            self.assertNotIn('PRIVATE_',str(result))
            self.assertEqual(before,s.DB.read_bytes())
            with s.db() as c:c.execute("UPDATE artifacts SET content='changed' WHERE id=?",(candidate,))
            self.assertEqual(campus_tools.read(s.DB,'improvements',{})['rows'][1]['candidate_identity'],'changed')
