import tempfile
import unittest
import sqlite3
from pathlib import Path
from test_campus_live import fixture
import campus_tools as t

class CampusToolTests(unittest.TestCase):
    def test_read_tools(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.db';fixture(p);before=p.read_bytes()
            def read(name,**params):return t.read(p,name,{k:[v] for k,v in params.items()})['rows']
            self.assertEqual(len(read('missions')),2)
            self.assertEqual(read('files')[0]['mode'],'demo')
            self.assertNotIn('content',read('files')[0])
            self.assertEqual(read('artifact',id='1')[0]['content'],'secret-test')
            self.assertEqual(len(read('memory',q='MNEMOS')),1)
            self.assertEqual(read('memory',q='%_'),[])
            self.assertEqual(read('report',id='1')[0]['content'],'Recherche de marché test')
            self.assertEqual(sum(x['committed_micro_usd'] for x in read('finance')),4000)
            self.assertEqual(read('opps')[0]['status'],'hypothèse')
            self.assertEqual(before,p.read_bytes())
            for name,params in [('delete',{}),('artifact',{'id':['-1']}),('files',{'q':['x']}),('memory',{'q':['a']}),('report',{'id':['1','2']})]:
                with self.assertRaises(t.BadQuery):t.read(p,name,params)
            with self.assertRaises(t.Missing):read('artifact',id='99')
            with sqlite3.connect(p) as db:db.execute('UPDATE artifacts SET content=?',('x'*(t.MAX_ARTIFACT_BYTES+1),))
            with self.assertRaises(t.TooLarge):read('artifact',id='1')

    def test_incident_projection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.db';fixture(p)
            with sqlite3.connect(p) as db:
                db.executescript("""
                CREATE TABLE incident_recoveries(campaign INTEGER PRIMARY KEY,mission INTEGER,task INTEGER,ledger INTEGER,diagnostic TEXT,created TEXT);
                INSERT INTO incident_recoveries VALUES(1,1,1,1,'HTTP 503','2026-01-01'),(2,1,1,2,'secret diagnostic','2026-01-02');
                UPDATE missions SET state='bloquée' WHERE id=1;
                """)
            before=p.read_bytes()
            r=t.read(p,'incidents',{})
            self.assertTrue(r['read_only'])
            self.assertEqual(r['limit'],101)
            self.assertEqual(r['rows'][0]['counts'],[{'mode':'cloud','state':'bloquée','count':1}])
            self.assertEqual(r['rows'][0]['recovery_count'],2)
            self.assertEqual(r['rows'][1]['kind'],'mission')
            self.assertEqual(r['rows'][2]['diagnostic'],'Diagnostic hors liste')
            self.assertEqual(r['rows'][3]['diagnostic'],'HTTP 503')
            self.assertNotIn('secret diagnostic',str(r))
            self.assertEqual(p.read_bytes(),before)
            with self.assertRaises(t.BadQuery):t.read(p,'incidents',{'replay':['true']})
