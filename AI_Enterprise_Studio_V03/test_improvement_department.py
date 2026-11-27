"""Comparison policy regression tests, no live browser or paid API."""
import json
import unittest
from unittest.mock import patch

import improvement as imp
import laboratory as lab
import verification as verifier
from departments import improvement_comparison as comparison


class ImprovementDepartmentTests(unittest.TestCase):
    def setUp(self):
        self.base={'name':'audit_catalogue.html','content':'<p>base</p>'}
        self.new={'name':'audit_catalogue.html','content':'<p>candidate</p>'}
        self.cfg={'html_sandbox_enabled':True}
        self.frozen={'replays':[{'proof':7,'spec':'fixture'}],'lab':3}
        self.old={'status':'passed','fixture_sha256':'fixture-hash',
                  'metrics':{'recall':1,'false_alert_share':0,'format_and_refusal_ok':True},
                  'cases':[{'name':'fixture','elapsed_ms':12}]}

    def candidate(self,**updates):
        return {**self.old,'metrics':dict(self.old['metrics']),
                'cases':[{'name':'fixture','elapsed_ms':999}],**updates}

    def compare(self,profile,observed,results):
        with patch.object(verifier,'run',side_effect=[{'status':x} for x in results]) as verify:
            with patch.object(lab,'evaluate',return_value=observed) as evaluate:
                state,result=imp.verify_pair(self.base,self.new,self.frozen,profile,self.cfg,self.old)
                self.assertEqual(verify.call_args_list[0].args,
                                 (self.new['name'],self.new['content'],'fixture',True))
                evaluate.assert_called_once_with(self.new,lab.PROFILE,300,lab.DEFAULT_SEED,True)
                return state,result,verify.call_count

    def test_generic_non_regression_requires_review_not_promotion(self):
        state,result,calls=self.compare('generic',self.candidate(),['passed'])
        self.assertEqual(state,'review')
        self.assertTrue(result['laboratory']['non_regression'])
        self.assertEqual(result['laboratory']['baseline_times'],[{'name':'fixture','elapsed_ms':12}])
        self.assertEqual(calls,1)

    def test_csv_feature_demonstrated_only_after_non_regression(self):
        state,result,calls=self.compare(imp.CSV_PROFILE,self.candidate(),['passed','failed','passed'])
        self.assertEqual(state,'retained')
        self.assertEqual(calls,3)
        self.assertEqual(result['feature']['baseline']['status'],'failed')
        self.assertEqual(result['feature']['candidate']['status'],'passed')

    def test_already_present_or_unavailable_baseline_requires_review(self):
        for before in ('passed','unavailable','invalid'):
            with self.subTest(before=before):
                state,result,calls=self.compare(imp.CSV_PROFILE,self.candidate(),['passed',before,'passed'])
                self.assertEqual(state,'review')
                self.assertEqual(calls,3)

    def test_failed_feature_rejects_candidate(self):
        for after in ('failed','unavailable','invalid'):
            with self.subTest(after=after):
                self.assertEqual(self.compare(imp.CSV_PROFILE,self.candidate(),['passed','failed',after])[0],'rejected')

    def test_regression_and_mismatched_fixtures_prevent_feature_execution(self):
        for observed in (self.candidate(fixture_sha256='different'),
                         self.candidate(metrics={'recall':.99,'false_alert_share':0,'format_and_refusal_ok':True}),
                         self.candidate(metrics={'recall':1,'false_alert_share':.01,'format_and_refusal_ok':True}),
                         self.candidate(metrics={'recall':1,'false_alert_share':0,'format_and_refusal_ok':False}),
                         self.candidate(status='unavailable',metrics=None)):
            with self.subTest(observed=observed):
                state,result,calls=self.compare(imp.CSV_PROFILE,observed,['passed'])
                self.assertEqual(state,'rejected')
                self.assertFalse(result['laboratory']['non_regression'])
                self.assertIsNone(result['feature'])
                self.assertEqual(calls,1)

    def test_failed_historical_replay_blocks_feature_even_with_good_lab(self):
        state,result,calls=self.compare(imp.CSV_PROFILE,self.candidate(),['failed'])
        self.assertEqual(state,'rejected')
        self.assertTrue(result['laboratory']['non_regression'])
        self.assertIsNone(result['feature'])
        self.assertEqual(calls,1)

    def test_fixed_feature_contract_and_live_legacy_callbacks(self):
        spec=imp.feature_spec()
        self.assertEqual(spec,comparison.feature_spec())
        self.assertEqual(len(verifier.html_spec(spec)),2)
        self.assertTrue(all(x['steps'][0]['op']=='upload' for x in spec['cases']))
        with patch.object(imp,'feature_spec',return_value=spec) as feature:
            with patch.object(verifier,'run',side_effect=[{'status':'failed'},{'status':'passed'}]) as run:
                state,result=imp.verify_pair(self.base,self.new,{'replays':[],'lab':None},imp.CSV_PROFILE,{},None)
                self.assertEqual(state,'retained')
                self.assertEqual(feature.call_count,2)
                raw=json.dumps(spec,ensure_ascii=False)
                self.assertEqual([x.args for x in run.call_args_list],
                                 [(self.base['name'],self.base['content'],raw,False),
                                  (self.new['name'],self.new['content'],raw,False)])


if __name__=='__main__':
    unittest.main()
