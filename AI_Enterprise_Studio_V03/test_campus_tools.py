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
