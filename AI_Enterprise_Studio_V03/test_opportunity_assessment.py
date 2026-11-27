"""Economic assessment and ranking contracts on a temporary real schema."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import intelligence as intel
import serveur as s


class OpportunityAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',root/'fixture.sqlite3'))
        s.init()
        self.mid=self.mission()
        self.oid=self.opportunity(self.mid,'Fixture A')
        self.base={'price_cents':2000,'variable_cost_cents':800,'fixed_month_cents':10000,
                   'monthly_units':20,'automation_pct':80,'risk':2,'source_runs':[],
                   'rationale':'Hypothèse de travail non certifiée.'}

    def mission(self,mode='cloud',state='en cours'):
        with s.db() as c:
            return c.execute('INSERT INTO missions(title,mode,state) VALUES(?,?,?)',
                             ('fixture',mode,state)).lastrowid

    def opportunity(self,mid,title):
        with s.db() as c:
            return c.execute('INSERT INTO opportunities(mission,title,body,next_test) VALUES(?,?,?,?)',
                             (mid,title,'Hypothèse fictive','Vérifier les besoins')).lastrowid

    def assess(self,oid=None,mid=None,agent='MIDAS',**changes):
        payload=dict(self.base,**changes)
        with s.db() as c:
            return intel.assess(c,self.mid if mid is None else mid,agent,
                                str(self.oid if oid is None else oid),json.dumps(payload))

    def complete(self,mid=None):
        with s.db() as c:
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",
                      (self.mid if mid is None else mid,))

    def ranked(self):
        with s.db() as c:
            return intel.ranking(c)

    def count(self):
        with s.db() as c:
            return c.execute('SELECT COUNT(*) FROM market_assessments').fetchone()[0]

    def test_exact_economics_and_hypothesis_classification(self):
        r=self.assess()
        self.assertEqual(r['contribution_cents'],1200)
        self.assertEqual(r['margin_bp'],6000)
        self.assertEqual(r['breakeven_units'],9)
        self.assertEqual(r['monthly_result_cents'],14000)
        self.assertEqual(r['components'],{'margin':24,'scenario':7,'automation':20,'risk':11})
        self.assertEqual(r['score'],62)
        self.assertTrue(r['scenario_viable'])
        self.assertEqual(r['classification'],'hypothèse non validée')
        self.assertIn('Aucune preuve de ventes',r['limit'])
        with s.db() as c:
            row=c.execute('SELECT * FROM market_assessments WHERE id=?',(r['assessment'],)).fetchone()
            self.assertEqual(json.loads(row['assumptions']),self.base)
            self.assertEqual(json.loads(row['result']),{k:v for k,v in r.items()
                                                        if k not in ('assessment','opportunity')})

    def test_nonviable_scenarios_score_zero(self):
        for changes,breakeven in [({'variable_cost_cents':2000},None),
                                  ({'variable_cost_cents':2500},None),
                                  ({'monthly_units':1},9),
                                  ({'fixed_month_cents':24000},20)]:
            with self.subTest(changes=changes):
                r=self.assess(**changes)
                self.assertEqual(r['score'],0)
                self.assertFalse(r['scenario_viable'])
                self.assertEqual(r['breakeven_units'],breakeven)

    def test_agent_scope_and_validation_before_write(self):
        foreign=self.opportunity(self.mission(),'Foreign')
        with self.assertRaisesRegex(ValueError,'Évaluation MIDAS'):
            self.assess(agent='ORION')
        with self.assertRaisesRegex(ValueError,'Opportunité de cette mission'):
            self.assess(oid=foreign)
        for changes in ({'price_cents':0},{'monthly_units':True},{'risk':6},
                        {'automation_pct':101},{'rationale':'short'},
                        {'source_runs':[1,1]},{'page_refs':[True]},
                        {'unexpected':'field'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.assess(**changes)
        self.assertEqual(self.count(),0)

    def test_six_assessment_limit_is_mission_scoped(self):
        for _ in range(6):
            self.assess()
        with self.assertRaisesRegex(ValueError,'Plafond de six'):
            self.assess()
        other=self.mission()
        self.assess(oid=self.opportunity(other,'Other'),mid=other)
        self.assertEqual(self.count(),7)

    def test_rank_latest_only_ties_and_mission_eligibility(self):
        other=self.opportunity(self.mid,'Fixture B')
        old=self.assess(automation_pct=100)
        newest=self.assess()
        tied=self.assess(oid=other)
        demo=self.mission('demo','terminée')
        self.assess(oid=self.opportunity(demo,'Demo'),mid=demo)
        self.assertEqual(self.ranked(),[])
        self.complete()
        ranked=self.ranked()
        self.assertEqual([r['id'] for r in ranked],[newest['assessment'],tied['assessment']])
        self.assertNotIn(old['assessment'],[r['id'] for r in ranked])
        self.assertEqual([r['opportunity'] for r in ranked],[self.oid,other])

    def test_rank_score_order_and_project_state(self):
        other=self.opportunity(self.mid,'Fixture B')
        self.assess()
        better=self.assess(oid=other,automation_pct=100,risk=1)
        self.complete()
        self.assertEqual(self.ranked()[0]['id'],better['assessment'])
        with s.db() as c:
            c.execute('INSERT INTO projects(origin,title,opportunity,state) VALUES(?,?,?,?)',
                      ('fixture:other','Fixture B',other,'paused'))
        self.assertEqual([r['opportunity'] for r in self.ranked()],[self.oid])

    def test_modified_opportunity_invalidates_latest_assessment(self):
        self.assess()
        self.complete()
        self.assertEqual(len(self.ranked()),1)
        with s.db() as c:
            c.execute('UPDATE opportunities SET body=? WHERE id=?',('changed',self.oid))
        self.assertEqual(self.ranked(),[])

    def test_page_provenance_is_rechecked_during_ranking(self):
        url='https://example.invalid/fixture'
        with s.db() as c:
            rid=c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,?,'reçue',?)",
                          (self.mid,url,json.dumps({'url':url,'texte':'Original'}))).lastrowid
        result=self.assess(page_refs=[rid])
        self.assertEqual(result['page_count'],1)
        self.assertEqual(result['pages'][0]['id'],rid)
        self.complete()
        self.assertEqual(len(self.ranked()),1)
        with s.db() as c:
            c.execute('UPDATE fetched SET content=? WHERE id=?',
                      (json.dumps({'url':url,'texte':'Changed'}),rid))
        self.assertEqual(self.ranked(),[])

    def test_source_callbacks_rechecked_and_failures_do_not_write(self):
        with patch.object(intel,'source',side_effect=ValueError('fixture rejected')):
            with self.assertRaisesRegex(ValueError,'fixture rejected'):
                self.assess(source_runs=[7])
        self.assertEqual(self.count(),0)
        with patch.object(intel,'source',return_value={'fixture':True}) as source:
            result=self.assess(source_runs=[7])
            source.assert_called_once()
        self.assertEqual(result['evidence_count'],1)
        self.complete()
        with patch.object(intel,'source',return_value={'fixture':True}):
            self.assertEqual(len(self.ranked()),1)
        with patch.object(intel,'source',side_effect=ValueError('fixture changed')):
            self.assertEqual(self.ranked(),[])


if __name__=='__main__':
    unittest.main()
