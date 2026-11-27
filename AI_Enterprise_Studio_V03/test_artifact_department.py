"""Contracts for artifact lookup and static validation on the real schema."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import moteur as m
import serveur as s
from departments import artifacts


class ArtifactDepartmentTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('current','cloud','en cours')").lastrowid
            self.source=c.execute("INSERT INTO missions(title,mode,state) VALUES('source','cloud','terminée')").lastrowid
            self.demo=c.execute("INSERT INTO missions(title,mode,state) VALUES('demo','demo','terminée')").lastrowid
            self.old=self.add(c,self.mid,'fixture.json',1,'{}')
            self.new=self.add(c,self.mid,'fixture.json',2,'{"a":2}')
            self.ref=self.add(c,self.source,'fixture.json',4,'{"source":4}')
            self.demo_ref=self.add(c,self.demo,'fixture.json',1,'{"demo":1}')

    @staticmethod
    def add(c,mid,name,version,content):
        return c.execute('INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,?,?,?,?,?)',
                         (mid,name,version,'NEXUS',content,'fixture')).lastrowid

    def test_latest_version_and_mission_isolation(self):
        with s.db() as c:
            self.assertEqual(artifacts.latest(c,self.mid,'fixture.json')['id'],self.new)
            self.assertEqual(m.latest(c,self.source,'fixture.json')['id'],self.ref)
            self.assertIsNone(m.latest(c,self.mid,'absent.json'))
            self.assertIsNone(m.latest(c,self.mid,'Fixture.json'))
            row,reference=m.resolve_artifact(c,self.mid,'fixture.json')
            self.assertEqual(row['id'],self.new)
            self.assertFalse(reference)

    def test_exact_reference_read_only_metadata(self):
        with s.db() as c:
            c.execute('INSERT INTO mission_artifact_refs(mission,artifact) VALUES(?,?)',(self.mid,self.ref))
            row,reference=m.resolve_artifact(c,self.mid,'ref:'+str(self.ref))
            self.assertTrue(reference)
            self.assertEqual(row['id'],self.ref)
            self.assertEqual(m.reference_metadata(row),{
                'target':'ref:'+str(self.ref),'id':self.ref,'mission_source':self.source,
                'name':'fixture.json','version':4,'agent':'NEXUS','lecture_seule':True})
            with self.assertRaisesRegex(ValueError,'Référence non autorisée'):
                m.resolve_artifact(c,self.mid,'ref:'+str(self.new))
            with self.assertRaisesRegex(ValueError,'Référence non autorisée'):
                m.resolve_artifact(c,self.mid,'ref:0'+str(self.ref))

    def test_missing_and_demo_reference_refused(self):
        with s.db() as c:
            self.assertIsNone(m.attached_artifact(c,self.mid))
            with self.assertRaisesRegex(ValueError,'Référence non autorisée'):
                m.resolve_artifact(c,self.mid,'ref:'+str(self.ref))
            c.execute('INSERT INTO mission_artifact_refs(mission,artifact) VALUES(?,?)',(self.mid,self.demo_ref))
            self.assertIsNone(m.attached_artifact(c,self.mid))
            with self.assertRaisesRegex(ValueError,'Référence non autorisée'):
                m.resolve_artifact(c,self.mid,'ref:'+str(self.demo_ref))

    def test_queries_do_not_write_or_commit(self):
        with s.db() as c:
            before=c.total_changes
            c.execute('PRAGMA query_only=ON')
            try:
                self.assertEqual(m.latest(c,self.mid,'fixture.json')['id'],self.new)
                self.assertIsNone(m.attached_artifact(c,self.mid))
                self.assertEqual(c.total_changes,before)
            finally:
                c.execute('PRAGMA query_only=OFF')
        with self.assertRaisesRegex(RuntimeError,'fixture rollback'):
            with s.db() as c:
                aid=self.add(c,self.mid,'fixture.json',3,'{"a":3}')
                self.assertEqual(m.latest(c,self.mid,'fixture.json')['id'],aid)
                raise RuntimeError('fixture rollback')
        with s.db() as c:
            self.assertEqual(m.latest(c,self.mid,'fixture.json')['id'],self.new)

    def test_static_python_and_json_checks_do_not_execute(self):
        with patch('builtins.exec',side_effect=AssertionError('code execution')):
            self.assertTrue(m.check('script.PY','raise RuntimeError("never executed")')['valide'])
        self.assertFalse(m.check('script.py','def broken(')['valide'])
        self.assertTrue(m.check('fixture.json','{"a":1}')['valide'])
        self.assertFalse(m.check('fixture.json','{')['valide'])

    def test_csv_shape_and_empty_content(self):
        self.assertEqual(m.check('fixture.csv','a,b\n1,2')['controle'],'CSV rectangulaire : 2 lignes, 2 colonnes')
        self.assertFalse(m.check('fixture.csv','a,b\n1')['valide'])
        self.assertFalse(m.check('fixture.csv','')['valide'])
        self.assertFalse(m.check('fixture.txt','   ')['valide'])
        self.assertEqual(m.check('fixture.html','<script>throw 1</script>')['controle'],
                         'Contenu non vide; pas de validateur spécialisé')

    def test_legacy_dependencies_resolved_at_call_time(self):
        with s.db() as c:
            with patch.object(m,'latest',return_value={'id':77}) as latest:
                self.assertEqual(m.resolve_artifact(c,self.mid,'fixture.json'),({'id':77},False))
                latest.assert_called_once_with(c,self.mid,'fixture.json')
            with patch.object(m,'attached_artifact',return_value={'id':88}) as attached:
                self.assertEqual(m.resolve_artifact(c,self.mid,'ref:88'),({'id':88},True))
                attached.assert_called_once_with(c,self.mid)
        with patch.object(m.ast,'parse',side_effect=SyntaxError('fixture')) as parse:
            self.assertFalse(m.check('script.py','pass')['valide'])
            parse.assert_called_once_with('pass')

    def test_static_check_retains_explicit_limitations(self):
        valid=m.check('fixture.txt','content')
        invalid=m.check('fixture.json','{')
        self.assertEqual(valid['limite'],'Aucun code exécuté, aucun test fonctionnel ni conformité garantis.')
        self.assertEqual(invalid['limite'],'Contrôle statique uniquement.')


if __name__=='__main__':
    unittest.main()
