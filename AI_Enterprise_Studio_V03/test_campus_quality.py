import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools
import verification
import laboratory

class QualityTests(unittest.TestCase):
    def test_read_evidence_without_execution(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            s.init()
            content='a,b\n1,2\n'
            spec=json.dumps({'checks':[{'op':'sum','column':'b','expected':'2'}]})
            result=verification.run('kit.csv',content,spec)
            sha=hashlib.sha256(content.encode()).hexdigest()
            with s.db() as db:
                source=db.execute("INSERT INTO missions(title,mode,state) VALUES('Produit','cloud','terminée')").lastrowid
                test=db.execute("INSERT INTO missions(title,mode,state) VALUES('Test','cloud','terminée')").lastrowid
                aid=db.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',1,'NEXUS',?,'test')",(source,content)).lastrowid
                for payload in (result,{**result,'checks':[]},{**result,'sha256':'0'*64}):
                    db.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(aid,test,spec,json.dumps(payload)))
                lab={'status':'passed','sha256':sha,'profile':'catalogue-v1','revision':1,'size':100,'metrics':{'recall':1.0,'false_alert_share':0,'tp':14,'fp':0,'fn':0},'fixtures':['PRIVATE_FIXTURE']}
                db.execute("INSERT INTO laboratory_runs(artifact,profile,revision,size,seed,sha256,status,result) VALUES(?,'catalogue-v1',1,100,42,?,'passed',?)",(aid,sha,json.dumps(lab)))
            before=s.DB.read_bytes()
            with patch.object(verification,'run',side_effect=AssertionError('No test')),patch.object(laboratory,'evaluate',side_effect=AssertionError('No lab')),patch.object(s,'request',side_effect=AssertionError('No provider')):
                r=campus_tools.read(s.DB,'quality',{})
            self.assertTrue(r['read_only'])
            self.assertEqual(r['limit'],100)
            changed,bad,good,lab=r['rows']
            self.assertEqual(changed['identity'],'changed')
            self.assertEqual(bad['status'],'unreadable')
            self.assertEqual((good['status'],good['identity']),('passed','match'))
            self.assertEqual((good['mission'],good['source_mission']),(test,source))
            self.assertTrue(good['checks'][0]['passed'])
            self.assertEqual(lab['metrics']['recall'],1.0)
            self.assertNotIn('PRIVATE_FIXTURE',str(r))
            self.assertNotIn('spec',good)
            self.assertNotIn('content',good)
            self.assertEqual(before,s.DB.read_bytes())
            with self.assertRaises(campus_tools.BadQuery):campus_tools.read(s.DB,'quality',{'run':['true']})
            with s.db() as db:db.execute("UPDATE artifacts SET content='changed' WHERE id=?",(aid,))
            self.assertEqual(campus_tools.read(s.DB,'quality',{})['rows'][2]['identity'],'changed')
