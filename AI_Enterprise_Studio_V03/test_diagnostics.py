"""Diagnostic contracts on fictitious local data, no provider or real secrets."""
import json
import sqlite3
import unittest
import urllib.error
from contextlib import closing
from infrastructure import diagnostics as d


class DiagnosticTests(unittest.TestCase):
    def test_transport_error_excludes_raw_message(self):
        self.assertEqual(d.transport_error(RuntimeError('private-fixture')), 'RuntimeError')
        e=urllib.error.HTTPError('https://example.invalid/private-fixture', 429,
                                 'private-fixture', None, None)
        self.assertEqual(d.transport_error(e), 'HTTP 429')

    def test_token_detail_compatible(self):
        self.assertEqual(d.token_detail('ATLAS : incomplete',20,100,3),
                         'ATLAS : incomplete ; sortie 20/100 tokens ; raisonnement 3')
        self.assertEqual(d.token_detail('échec',0,100,None),
                         'échec ; sortie 0/100 tokens ; raisonnement non communiqué')

    def test_json_error_is_structural(self):
        try:
            json.loads('{"private-fixture": }')
        except json.JSONDecodeError as e:
            self.assertEqual(d.invalid_json(e),
                             f'JSON non décodable (ligne {e.lineno}, colonne {e.colno})')
            self.assertNotIn('private-fixture',d.invalid_json(e))
        else:
            self.fail('Expected invalid JSON')

    def fixture(self,c):
        c.row_factory=sqlite3.Row
        c.executescript("""
        CREATE TABLE missions(id INTEGER PRIMARY KEY,title TEXT);
        CREATE TABLE tasks(id INTEGER PRIMARY KEY,mission INTEGER,agent TEXT,state TEXT,turns INTEGER);
        CREATE TABLE events(id INTEGER PRIMARY KEY,mission INTEGER,task INTEGER,agent TEXT,action TEXT,args TEXT,result TEXT,ok INTEGER,created TEXT);
        CREATE TABLE ledger(mission INTEGER,actual INTEGER,reserved INTEGER);
        INSERT INTO missions VALUES(1,'fixture'),(2,'other');
        INSERT INTO tasks VALUES(1,1,'ATLAS','terminée',3),(2,2,'ORION','en cours',1);
        INSERT INTO ledger VALUES(1,500,1000),(1,NULL,250),(2,9999,9999);
        """)
        c.executemany('INSERT INTO events VALUES(?,1,1,?,?,?,?,1,?)',
                      [(i,'ATLAS','fixture','a'*700,'r'*900,'fixture') for i in range(1,106)])
        c.execute("INSERT INTO events VALUES(106,2,2,'ORION','other','other','other',1,'fixture')")
        c.commit()

    def test_mission_projection_bounds_and_cost(self):
        with closing(sqlite3.connect(':memory:')) as c:
            self.fixture(c)
            c.execute('PRAGMA query_only=ON')
            result=d.mission(c,1)
            self.assertEqual(set(result),{'mission','tasks','events','calls','estimated_usd','limit'})
            self.assertEqual(result['mission'],{'id':1,'title':'fixture'})
            self.assertEqual(result['tasks'],[{'id':1,'agent':'ATLAS','state':'terminée','turns':3}])
            self.assertEqual(result['calls'],2)
            self.assertEqual(result['estimated_usd'],.00075)
            self.assertEqual(len(result['events']),100)
            self.assertEqual([e['id'] for e in result['events']],list(range(105,5,-1)))
            self.assertEqual(len(result['events'][0]['args']),600)
            self.assertEqual(len(result['events'][0]['result']),800)
            self.assertEqual(result['limit'],'Extraits de journal local; vérifier avant partage.')

    def test_missing_and_empty_mission(self):
        with closing(sqlite3.connect(':memory:')) as c:
            self.fixture(c)
            c.execute("INSERT INTO missions VALUES(3,'empty')")
            result=d.mission(c,3)
            self.assertEqual((result['calls'],result['estimated_usd'],result['tasks'],result['events']),
                             (0,0,[],[]))
            with self.assertRaisesRegex(ValueError,'Mission absente'):
                d.mission(c,99)


if __name__ == '__main__':
    unittest.main()
