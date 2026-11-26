import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import campus_tools as t
import campus_infrastructure as i

class InfrastructureTests(unittest.TestCase):
    def test_inventory_read_only(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
            root=Path(d);s.init()
            (root/'PREPARATION.json').write_text(json.dumps({'schema':'aes.update.preflight.v1','integrity':'ok','protected_tables':{'missions':5,'private-secret':99},'secret':'PRIVATE_REPORT','source_unchanged':True}),encoding='utf8')
            (root/'BUILD_INFO.json').write_text(json.dumps({'commit':'a'*40,'private':'PRIVATE_BUILD'}),encoding='utf8')
            cfg={'key':'PRIVATE_KEY','brave':'','html_sandbox_enabled':False}
            resources=i.metadata(root,'3.0.0',cfg,True,True)
            with s.db() as db:
                db.execute("UPDATE connector_policies SET enabled=1,max_calls=2 WHERE capability='github.public_repo'")
                db.execute("INSERT INTO connector_runs(capability,actor,input_sha256,reserved,state,diagnostic) VALUES('github.public_repo','PROPRIETAIRE','PRIVATE_HASH',0,'received','PRIVATE_DIAGNOSTIC')")
            before=s.DB.read_bytes()
            with patch.object(s,'request',side_effect=AssertionError('No provider')) as network:
                r=t.read(s.DB,'infrastructure',{},resources=resources,registry=s.connectors.REGISTRY)
                network.assert_not_called()
            self.assertTrue(r['read_only'])
            self.assertEqual(r['limit'],1+len(s.connectors.REGISTRY))
            runtime=r['rows'][0]
            self.assertEqual(runtime['mode'],'preview')
            self.assertTrue(runtime['database_readable'])
            self.assertEqual(runtime['tables_missing'],[])
            self.assertIsNone(runtime['backup_verified'])
            self.assertIsNone(runtime['integrity_verified_now'])
            self.assertEqual(runtime['preparation']['protected_tables'],{'missions':5})
            self.assertEqual(runtime['packaged_commit'],'a'*40)
            github=next(x for x in r['rows'][1:] if x['id']=='github.public_repo')
            self.assertTrue(github['authorized'])
            self.assertEqual(github['last']['state'],'received')
            self.assertIsNone(github['availability_verified_now'])
            self.assertNotIn('PRIVATE',json.dumps(r))
            self.assertEqual(s.DB.read_bytes(),before)
            with self.assertRaises(t.BadQuery):t.read(s.DB,'infrastructure',{'path':['config.json']})
            (root/'PREPARATION.json').write_text('x'*(i.MAX_MANIFEST+1),encoding='utf8')
            self.assertIsNone(i.metadata(root,'3.0.0',cfg,False,False)['preparation'])
            (root/'BUILD_INFO.json').write_text('not json',encoding='utf8')
            self.assertIsNone(i.metadata(root,'3.0.0',cfg,False,False)['packaged_commit'])
