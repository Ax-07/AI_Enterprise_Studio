"""Source integrity and transaction contracts on the real application schema."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import intelligence as intel
import serveur as s


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','en cours')").lastrowid
            self.other=c.execute("INSERT INTO missions(title,mode,state) VALUES('other','cloud','en cours')").lastrowid
        spec={'countries':['FRA','GBR'],'year':2023}
        rows=[{'countryiso3code':country,'indicator':{'id':indicator},'date':'2023','value':value}
              for country in spec['countries']
              for indicator,value in [('SP.POP.TOTL',100),('IT.NET.USER.ZS',80)]]
        raw=json.dumps([{'page':1,'pages':1,'total':len(rows)},rows])
        snapshot=intel.parse(raw.encode(),spec)
        self.result={'source':'fixture WDI','url':intel.url_for(spec),
                     'retrieved':'2025-01-01T00:00:00+00:00',
                     'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                     'snapshot':snapshot,'snapshot_sha256':intel.digest(snapshot),'raw_json':raw}

    def run_id(self,mid=None,state='received',cap=None):
        with s.db() as c:
            return c.execute('INSERT INTO connector_runs(capability,mission,actor,input_sha256,reserved,state) VALUES(?,?,?,?,?,?)',
                (intel.CAP if cap is None else cap,self.mid if mid is None else mid,
                 'ORION','fixture',0,state)).lastrowid

    def record(self,mid=None,state='received',cap=None):
        rid=self.run_id(mid,state,cap)
        with s.db() as c:
            intel.record(c,rid,self.result)
        return rid

    def page(self,content,state='reçue',mid=None):
        with s.db() as c:
            return c.execute('INSERT INTO fetched(mission,url,state,content) VALUES(?,?,?,?)',
                (self.mid if mid is None else mid,'https://example.invalid/fixture',state,json.dumps(content))).lastrowid

    def test_record_roundtrip_and_raw_integrity(self):
        rid=self.record()
        with s.db() as c:
            row=c.execute('SELECT * FROM market_sources WHERE run=?',(rid,)).fetchone()
            self.assertEqual(intel.source(c,rid,self.mid),self.result['snapshot'])
            self.assertEqual(intel.raw_integrity(c,row,self.result['snapshot']),(True,self.result['raw_json']))
            self.assertEqual(intel.sources(c,self.mid)[0]['run'],rid)

    def test_invalid_hash_or_projection_rejected_before_writes(self):
        for field,value,reason in [('raw_sha256','invalid','Empreinte'),
            ('snapshot_sha256','invalid','Empreinte'),('url','https://example.invalid','Projection')]:
            with self.subTest(field=field):
                rid=self.run_id()
                result=deepcopy(self.result)
                result[field]=value
                with s.db() as c:
                    with self.assertRaisesRegex(ValueError,reason):
                        intel.record(c,rid,result)
                    self.assertIsNone(c.execute('SELECT 1 FROM market_sources WHERE run=?',(rid,)).fetchone())
                    self.assertIsNone(c.execute('SELECT 1 FROM market_source_raw WHERE run=?',(rid,)).fetchone())

    def test_source_requires_matching_mission_state_and_capability(self):
        ids=[self.record(mid=self.other),self.record(state='failed'),self.record(cap='github.public_repo')]
        with s.db() as c:
            for rid in ids:
                with self.subTest(rid=rid), self.assertRaisesRegex(ValueError,'Source officielle reçue'):
                    intel.source(c,rid,self.mid)

    def test_tampered_raw_and_missing_raw_are_not_sources(self):
        rid=self.record()
        with s.db() as c:
            c.execute('UPDATE market_source_raw SET raw_json=? WHERE run=?',('[]',rid))
            with self.assertRaisesRegex(ValueError,'Empreinte ou projection'):
                intel.source(c,rid,self.mid)
            c.execute('DELETE FROM market_source_raw WHERE run=?',(rid,))
            row=c.execute('SELECT * FROM market_sources WHERE run=?',(rid,)).fetchone()
            self.assertEqual(intel.raw_integrity(c,row,self.result['snapshot']),(False,None))
            self.assertEqual(intel.sources(c,self.mid),[])

    def test_latest_three_rows_window_and_invalid_skipping(self):
        ids=[self.record() for _ in range(4)]
        with s.db() as c:
            c.execute('UPDATE market_sources SET snapshot_sha256=? WHERE run=?',('invalid',ids[-1]))
            self.assertEqual([x['run'] for x in intel.sources(c,self.mid)],[ids[-2],ids[-3]])

    def test_transaction_rolls_back_when_raw_insert_fails(self):
        rid=self.run_id()
        with s.db() as c:
            c.execute("CREATE TRIGGER fixture_fail BEFORE INSERT ON market_source_raw BEGIN SELECT RAISE(ABORT,'fixture'); END")
        import sqlite3
        with self.assertRaisesRegex(sqlite3.IntegrityError,'fixture'):
            with s.db() as c:
                intel.record(c,rid,self.result)
        with s.db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM market_sources WHERE run=?',(rid,)).fetchone())

    def test_page_reference_hash_and_scope(self):
        data={'url':'https://example.invalid/fixture','texte':'Économie\n25 EUR','partiel':True,'date':'fixture-date'}
        rid=self.page(data)
        other=self.page(data,mid=self.other)
        bad=self.page(dict(data,url='https://example.invalid/other'))
        failed=self.page(data,state='échec')
        with s.db() as c:
            row=intel.page_reference(c,self.mid,rid)
            self.assertEqual(row['excerpt_sha256'],hashlib.sha256(data['texte'].encode()).hexdigest())
            self.assertEqual(row['date'],'fixture-date')
            self.assertTrue(row['partial'])
            for invalid in (other,bad,failed):
                with self.assertRaises(ValueError):
                    intel.page_reference(c,self.mid,invalid)
            self.assertEqual([x['id'] for x in intel.page_refs(c,self.mid)],[rid])

    def test_legacy_callbacks_remain_live(self):
        rid=self.record()
        with s.db() as c:
            with patch.object(intel,'raw_integrity',return_value=(False,None)) as check:
                with self.assertRaisesRegex(ValueError,'Empreinte ou projection'):
                    intel.source(c,rid,self.mid)
                check.assert_called_once()
            with patch.object(intel,'source',return_value={'fixture':True}) as source:
                self.assertEqual(intel.sources(c,self.mid)[0]['snapshot'],{'fixture':True})
                source.assert_called_once_with(c,rid,self.mid)


if __name__=='__main__':
    unittest.main()
