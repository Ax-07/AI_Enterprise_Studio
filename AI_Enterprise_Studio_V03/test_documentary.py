"""Documentary service compatibility, using the real application schema."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research
import serveur as s
from departments import documentary


class DocumentaryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        self.mid=1
        self.raw='Introduction '*15+' Prix 25 EUR par mois.\n'+ 'Détail '*30+' manual errors '+ 'Fin '*40

    def page(self,content,state='reçue',mid=1):
        with s.db() as c:
            return c.execute('INSERT INTO fetched(mission,url,state,content) VALUES(?,?,?,?)',
                             (mid,'https://example.invalid/fixture',state,content)).lastrowid

    def search(self,result,status='reçue',mid=1):
        with s.db() as c:
            return c.execute('INSERT INTO searches(mission,query,status,result) VALUES(?,?,?,?)',
                             (mid,'fixture',status,result)).lastrowid

    def report(self,full=False):
        with s.db() as c:
            return research.mission(c,self.mid,full)

    def candidates(self):
        with s.db() as c:
            return research.exact_candidates(c,self.mid)

    def test_quality_threshold_and_precedence(self):
        for value,expected in [('x'*119,'short_excerpt'),(' '*10+'x'*120,'text_available'),
                               ('loading...','short_excerpt'),('LOADING...'+'x'*120,'possible_dynamic_shell')]:
            with self.subTest(expected=expected):
                self.assertEqual(research.excerpt_quality(value),expected)
                self.assertEqual(documentary.excerpt_quality(value),expected)

    def test_search_scope_order_and_full_limit(self):
        rows=[{'url':str(i)} for i in range(7)]
        first=self.search(json.dumps(rows))
        second=self.search('{}','échec')
        self.search('[]',mid=2)
        summary=self.report()
        self.assertEqual([x['id'] for x in summary['searches']],[first,second])
        self.assertEqual([x['result_count'] for x in summary['searches']],[7,0])
        self.assertEqual(summary['searches_received'],1)
        self.assertNotIn('unverified_results',summary['searches'][0])
        self.assertEqual(self.report(True)['searches'][0]['unverified_results'],rows[:5])

    def test_page_hash_partial_and_visibility(self):
        pid=self.page(json.dumps({'texte':self.raw,'partiel':True}))
        self.page(json.dumps({'texte':'other mission'}),mid=2)
        summary=self.report()
        page,=summary['pages']
        self.assertEqual(page['id'],pid)
        self.assertEqual(page['chars'],len(self.raw))
        self.assertEqual(page['excerpt_sha256'],hashlib.sha256(self.raw.encode()).hexdigest())
        self.assertTrue(page['partial'])
        self.assertEqual(page['quality'],'text_available')
        self.assertNotIn('excerpt',page)
        self.assertEqual(self.report(True)['pages'][0]['excerpt'],self.raw)

    def test_invalid_and_historical_rows_are_safe_projections(self):
        self.search('{')
        self.page('{')
        self.page('[]','échec')
        self.page(json.dumps({'failure':{'code':'timeout'}}),'échec')
        report=self.report()
        self.assertEqual(report['searches'][0]['result_count'],0)
        self.assertEqual(report['pages'][0]['quality'],'short_excerpt')
        self.assertEqual(report['pages'][1]['failure']['code'],'historical_unknown')
        self.assertEqual(report['pages'][2]['failure'],{'code':'timeout'})
        self.assertEqual(report['pages_received'],1)

    def test_candidates_are_exact_bounded_and_mission_scoped(self):
        ids=[self.page(json.dumps({'texte':self.raw})) for _ in range(4)]
        self.page(json.dumps({'texte':self.raw}),mid=2)
        self.page(json.dumps({'texte':self.raw}),'échec')
        result=self.candidates()
        self.assertEqual([x['page'] for x in result],list(reversed(ids[-3:])))
        for page in result:
            self.assertEqual(page['sha256'],hashlib.sha256(self.raw.encode()).hexdigest())
            self.assertTrue(1<=len(page['candidates'])<=4)
            for item in page['candidates']:
                start=item['offset']
                self.assertEqual(item['quote'],self.raw[start:start+len(item['quote'])])
                self.assertGreaterEqual(len(item['quote']),12)

    def test_recent_unusable_pages_do_not_expand_scan(self):
        self.page(json.dumps({'texte':self.raw}))
        self.page(json.dumps({'texte':'EUR'}))
        self.page(json.dumps({'texte':'loading...'+self.raw}))
        self.page('{')
        self.assertEqual(self.candidates(),[])

    def test_live_legacy_quality_callback_and_read_only_queries(self):
        self.page(json.dumps({'texte':self.raw}))
        with patch.object(research,'excerpt_quality',return_value='fixture') as quality:
            self.assertEqual(self.report()['pages'][0]['quality'],'fixture')
            self.assertEqual(self.candidates(),[])
            self.assertEqual(quality.call_count,2)
        with s.db() as c:
            before=c.total_changes
            self.assertEqual(documentary.mission(c,self.mid,quality=research.excerpt_quality),
                             research.mission(c,self.mid))
            self.assertEqual(c.total_changes,before)


if __name__=='__main__':
    unittest.main()
