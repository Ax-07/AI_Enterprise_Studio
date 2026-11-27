"""Recovery evidence contracts using the actual server schema and offline fixtures."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import autopilot
import draft_recovery as recovery
import portfolio
import serveur as s
from departments import recovery_evidence


class RecoveryDepartmentTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        with s.db() as c:
            self.pid=c.execute("INSERT INTO projects(origin,title) VALUES('fixture','Fixture')").lastrowid
            self.mid=c.execute("INSERT INTO missions(title,mode,state,engine,error) VALUES('fixture','cloud','bloquée','dynamic','Enveloppe Autopilote insuffisante pour réserver cet appel.')").lastrowid
            self.cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('fixture',1000,1,'{}',0,'bloqué')").lastrowid
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'create')",(self.cid,self.mid))
            portfolio.attach(c,self.mid,self.pid,'fixture')
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'draft.json',1,'NEXUS','{}','fixture')",(self.mid,)).lastrowid
            a=c.execute('SELECT * FROM artifacts WHERE id=?',(self.aid,)).fetchone()
            self.sha=recovery.sha(a)
            c.execute("INSERT INTO events(mission,agent,action,args,result,ok) VALUES(?,'NEXUS','write_file',?,?,1)",
                      (self.mid,json.dumps({'text_sha256':self.sha}),json.dumps({'fichier':self.aid})))

    def test_exact_candidate_and_read_only(self):
        with s.db() as c:
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                self.assertEqual(recovery.candidates(c),[{
                    'artifact':self.aid,'name':'draft.json','sha256':self.sha,
                    'source_mission':self.mid,'source_campaign':self.cid,'project':self.pid,'size':2}])
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')

    def test_missing_or_changed_write_evidence_refused(self):
        with s.db() as c:
            c.execute("UPDATE artifacts SET content='[]' WHERE id=?",(self.aid,))
            self.assertEqual(recovery.candidates(c),[])
            c.execute("UPDATE artifacts SET content='{}' WHERE id=?",(self.aid,))
            c.execute("UPDATE events SET args='{}' WHERE mission=?",(self.mid,))
            self.assertEqual(recovery.candidates(c),[])

    def test_unmeasured_cost_and_nonbudget_error_refused(self):
        with s.db() as c:
            rid=c.execute("INSERT INTO ledger(mission,model,reserved,state) VALUES(?,'fixture',100,'à rapprocher')",(self.mid,)).lastrowid
            self.assertEqual(recovery.candidates(c),[])
            c.execute("UPDATE ledger SET actual=0,state='mesuré' WHERE id=?",(rid,))
            self.assertEqual(len(recovery.candidates(c)),1)
            c.execute("UPDATE missions SET error='fixture other error' WHERE id=?",(self.mid,))
            self.assertEqual(recovery.candidates(c),[])

    def test_latest_version_and_existing_product_exclude_recovery(self):
        with s.db() as c:
            c.execute("INSERT INTO artifacts(mission,name,version,agent,content) VALUES(?,'draft.json',2,'NEXUS','[]')",(self.mid,))
            self.assertEqual(recovery.candidates(c),[])
            c.execute("DELETE FROM artifacts WHERE mission=? AND version=2",(self.mid,))
            with patch.object(portfolio,'latest',return_value={'id':999}) as latest:
                self.assertEqual(recovery.candidates(c),[])
                latest.assert_called_once_with(c,self.pid)

    def audit(self,c):
        cid=c.execute("INSERT INTO campaigns(goal,budget,max_missions,permissions,search_cap,state) VALUES('audit',1000,1,'{}',0,'actif')").lastrowid
        c.execute("INSERT INTO draft_recoveries(artifact,sha256,source_mission,source_campaign,project,campaign,budget) VALUES(?,?,?,?,?,?,1000)",
                  (self.aid,self.sha,self.mid,self.cid,self.pid,cid))
        row=recovery.record(c,cid)
        return cid,row

    def test_one_audit_and_integrity_guard(self):
        with s.db() as c:
            cid,row=self.audit(c)
            self.assertEqual(recovery.candidates(c),[])
            self.assertEqual(recovery.choose(c,cid),('functional',self.aid,None))
            self.assertEqual(recovery.verdict(c,row),'active')
            c.execute("UPDATE artifacts SET content='[]' WHERE id=?",(self.aid,))
            self.assertEqual(recovery.verdict(c,row),'modified')
            with self.assertRaisesRegex(ValueError,'Empreinte du brouillon modifiée'):
                recovery.choose(c,cid)

    def test_independent_exact_proof_required_for_adoption(self):
        with s.db() as c:
            cid,row=self.audit(c)
            c.execute("UPDATE campaigns SET state='terminé' WHERE id=?",(cid,))
            self.assertEqual(recovery.verdict(c,row),'incomplete')
            mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('audit','cloud','terminée')").lastrowid
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'functional',?)",(cid,mid,self.aid))
            self.assertEqual(recovery.verdict(c,row),'missing')
            proof={'sha256':self.sha,'status':'passed','checks':[{'passed':True}]}
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'NEXUS','{}',?)",
                      (self.aid,mid,json.dumps(proof)))
            self.assertEqual(recovery.verdict(c,row),'missing')
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL','{}',?)",
                      (self.aid,mid,json.dumps(proof)))
            self.assertEqual(recovery.verdict(c,row),'adopted')
            self.assertEqual(recovery.adopted(c,self.pid)['id'],self.aid)
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(self.mid,)).fetchone()[0],'bloquée')

    def test_live_legacy_dependencies(self):
        with s.db() as c:
            cid,row=self.audit(c)
            with patch.object(recovery_evidence,'verdict',return_value='fixture') as verdict:
                self.assertEqual(recovery.verdict(c,row),'fixture')
                verdict.assert_called_once_with(c,row,sha=recovery.sha,campaign=autopilot._campaign,
                                                missions=autopilot._missions,proof=autopilot._proof)


if __name__=='__main__':
    unittest.main()
