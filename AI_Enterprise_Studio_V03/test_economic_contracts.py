"""Transverse economic evidence contracts using synthetic transport and real SQLite."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import intelligence as intel
import research
import serveur as s


class EconomicFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        self.https=self.stack.enter_context(patch.object(intel.http.client,'HTTPSConnection'))
        self.stack.enter_context(patch('socket.create_connection',side_effect=AssertionError('unexpected network')))
        s.init()
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','en cours')").lastrowid
            self.other=c.execute("INSERT INTO missions(title,mode,state) VALUES('other','cloud','en cours')").lastrowid
            self.oid=c.execute('INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,?,?)',
                               (self.mid,'Fixture','Hypothèse fictive','Étudier les besoins')).lastrowid
        self.spec={'countries':['GBR','FRA'],'year':2023}
        rows=[{'countryiso3code':country,'indicator':{'id':key},'date':'2023','value':value}
              for country,pop,pct in [('GBR',67000000,90.125),('FRA',68000000,85.555)]
              for key,value in [('SP.POP.TOTL',pop),('IT.NET.USER.ZS',pct)]]
        self.raw=json.dumps([{'page':1,'pages':1,'total':len(rows)},rows]).encode()
        response=self.https.return_value.getresponse.return_value
        response.status=200
        response.read.return_value=self.raw
        self.url='https://example.invalid/fixture'
        self.excerpt='Introduction '*15+' Prix 25 EUR par mois.\n'+' Détail '*30
        self.assumptions={'price_cents':2000,'variable_cost_cents':800,
                          'fixed_month_cents':10000,'monthly_units':20,
                          'automation_pct':80,'risk':2,'rationale':'Hypothèse de travail non certifiée.'}

    def collect_fixture(self):
        # Real adapter and normalization; the received connector journal is a fixture.
        result=intel.fetch(json.dumps(self.spec))
        self.assertEqual(result['raw_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result['snapshot_sha256'],intel.digest(result['snapshot']))
        self.assertEqual(result['snapshot']['countries'],['FRA','GBR'])
        self.https.assert_called_once()
        self.https.return_value.close.assert_called_once()
        self.https.return_value.getresponse.return_value.read.assert_called_once_with(intel.MAX_BYTES+1)
        with s.db() as c:
            rid=c.execute('INSERT INTO connector_runs(capability,mission,actor,input_sha256,reserved,state) VALUES(?,?,?,?,?,?)',
                          (intel.CAP,self.mid,'ORION','fixture',0,'received')).lastrowid
            intel.record(c,rid,result)
            pid=c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,?,'reçue',?)",
                          (self.mid,self.url,json.dumps({'url':self.url,'texte':self.excerpt,'partiel':True}))).lastrowid
        return rid,pid

    def assess(self,c,rid,pid,oid=None,mid=None):
        return intel.assess(c,self.mid if mid is None else mid,'MIDAS',
                            str(self.oid if oid is None else oid),
                            json.dumps(dict(self.assumptions,source_runs=[rid],page_refs=[pid])))

    def completed(self):
        rid,pid=self.collect_fixture()
        with s.db() as c:
            result=self.assess(c,rid,pid)
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(self.mid,))
        return rid,pid,result

    def test_complete_chain_documentary_macro_provenance_assessment_and_status(self):
        rid,pid=self.collect_fixture()
        with s.db() as c:
            documentary=research.mission(c,self.mid)
            page,=documentary['pages']
            exact,=research.exact_candidates(c,self.mid)
            self.assertEqual((page['id'],exact['page']),(pid,pid))
            self.assertEqual(page['excerpt_sha256'],exact['sha256'])
            for item in exact['candidates']:
                start=item['offset']
                self.assertEqual(self.excerpt[start:start+len(item['quote'])],item['quote'])
            compare=intel.decode(intel.compare_input(c,json.dumps({'source_run':rid}),self.mid))
            self.assertEqual(compare['rows'],[
                {'country':'FRA','population':68000000,'internet_bp':8556},
                {'country':'GBR','population':67000000,'internet_bp':9013}])
            result=self.assess(c,rid,pid)
            self.assertEqual(result['pages'][0]['excerpt_sha256'],exact['sha256'])
            self.assertEqual((result['score'],result['evidence_count'],result['page_count']),(62,1,1))
            self.assertEqual(result['classification'],'hypothèse non validée')
            self.assertEqual(intel.ranking(c),[])
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(self.mid,))
            before=c.total_changes
            status=intel.status(c)
            self.assertEqual(status['ranking'][0]['id'],result['assessment'])
            self.assertTrue(status['sources'][0]['integrity'])
            self.assertTrue(status['sources'][0]['raw_preserved'])
            self.assertNotIn('raw_json',status['sources'][0])
            self.assertEqual(intel.status(c,True)['sources'][0]['raw_json'],self.raw.decode())
            self.assertEqual(c.total_changes,before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)

    def test_raw_tamper_invalidates_comparison_and_ranking(self):
        rid,pid,result=self.completed()
        with s.db() as c:
            self.assertEqual(intel.ranking(c)[0]['id'],result['assessment'])
            c.execute('UPDATE market_source_raw SET raw_json=? WHERE run=?',('[]',rid))
            self.assertFalse(intel.status(c)['sources'][0]['integrity'])
            self.assertEqual(intel.ranking(c),[])
            with self.assertRaisesRegex(ValueError,'Empreinte ou projection'):
                intel.compare_input(c,json.dumps({'source_run':rid}),self.mid)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM market_assessments').fetchone()[0],1)

    def test_page_tamper_invalidates_ranking_not_macro_source(self):
        rid,pid,result=self.completed()
        with s.db() as c:
            c.execute('UPDATE fetched SET content=? WHERE id=?',
                      (json.dumps({'url':self.url,'texte':self.excerpt+' modifié','partiel':True}),pid))
            self.assertTrue(intel.status(c)['sources'][0]['integrity'])
            self.assertEqual(intel.ranking(c),[])
            self.assertNotEqual(research.mission(c,self.mid)['pages'][0]['excerpt_sha256'],
                                result['pages'][0]['excerpt_sha256'])
            self.assertTrue(intel.comparable(intel.source(c,rid,self.mid)))

    def test_mission_boundary_refuses_reuse_without_writes(self):
        rid,pid=self.collect_fixture()
        with s.db() as c:
            foreign=c.execute('INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,?,?)',
                              (self.other,'Foreign','Fixture','Fixture')).lastrowid
            with self.assertRaisesRegex(ValueError,'Source officielle reçue'):
                self.assess(c,rid,pid,oid=foreign,mid=self.other)
            with self.assertRaisesRegex(ValueError,'Page effectivement lue'):
                intel.page_reference(c,self.other,pid)
            self.assertEqual(research.mission(c,self.other)['pages'],[])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM market_assessments').fetchone()[0],0)

    def test_invalid_transport_projection_is_rejected_and_connection_closed(self):
        self.https.return_value.getresponse.return_value.read.return_value=b'[{},[]]'
        with self.assertRaisesRegex(ValueError,'Pagination'):
            intel.fetch(json.dumps(self.spec))
        self.https.return_value.close.assert_called_once()
        with s.db() as c:
            for table in ('market_sources','market_source_raw','market_assessments'):
                self.assertEqual(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
