"""Independent synthetic benchmarks and historical laboratory boundaries."""
import json
import unittest
from unittest.mock import patch

import laboratory as lab
import verification as verifier
from departments import laboratory_benchmarks as benchmarks


def capture(fixtures):
    return [{'name':f['name'],'passed':True,'elapsed_ms':25,
             'output':f['expected_error'] if 'expected_error' in f else '\n'.join(f['expected']+[f['total']])}
            for f in fixtures]


class LaboratoryDepartmentTests(unittest.TestCase):
    def test_all_supported_sizes_and_seed_reproducibility(self):
        for size in lab.SIZES:
            with self.subTest(size=size):
                fixtures=lab.catalogue(size,42)
                self.assertEqual(fixtures,lab.catalogue(size,42))
                self.assertNotEqual(fixtures,lab.catalogue(size,43))
                self.assertEqual(len(json.loads(fixtures[0]['input'])['rows']),size)
                self.assertEqual(len(fixtures[1]['expected']),size*14//100)
                self.assertEqual(fixtures[1]['total'],f'TOTAL | P1 {size*10//100} | P2 {size*4//100}')
                self.assertEqual(lab.score(fixtures,capture(fixtures))['status'],'passed')

    def test_seed_and_size_types_are_strict(self):
        for size,seed in ((True,42),(101,42),(300,True),(300,-1),(300,2147483648)):
            with self.subTest(size=size,seed=seed):
                with self.assertRaisesRegex(ValueError,'Taille ou graine hors limites'):
                    lab.catalogue(size,seed)
        self.assertEqual(len(lab.catalogue(100,2147483647)),3)

    def test_duplicate_alerts_count_as_false_positives(self):
        fixtures=lab.catalogue(300,42)
        observed=capture(fixtures)
        lines=observed[1]['output'].splitlines()
        lines.insert(0,lines[0])
        lines[-1]='TOTAL | P1 31 | P2 12'
        observed[1]['output']='\n'.join(lines)
        result=lab.score(fixtures,observed)
        self.assertEqual((result['metrics']['tp'],result['metrics']['fp'],result['metrics']['fn']),(42,1,0))
        self.assertEqual(result['cases'][1]['status'],'failed')
        self.assertEqual(result['status'],'passed')
        self.assertTrue(result['metrics']['format_and_refusal_ok'])

    def test_bad_total_and_refusal_fail_even_with_perfect_alerts(self):
        fixtures=lab.catalogue(300,42)
        for index,output in ((0,'TOTAL | P1 1 | P2 0'),(2,'accepted')):
            observed=capture(fixtures)
            observed[index]['output']=output
            result=lab.score(fixtures,observed)
            self.assertEqual(result['metrics']['recall'],1)
            self.assertEqual(result['metrics']['false_alert_share'],0)
            self.assertFalse(result['metrics']['format_and_refusal_ok'])
            self.assertEqual(result['status'],'failed')

    def test_invalid_capture_and_unavailable_are_distinct(self):
        fixtures=lab.catalogue(100,42)
        for field,value in (('elapsed_ms',float('nan')),('elapsed_ms',True),('elapsed_ms',10001),
                            ('output','x'*24001),('name','unexpected'),('passed',1)):
            observed=capture(fixtures)
            observed[0][field]=value
            with self.subTest(field=field,value=str(value)[:30]):
                with self.assertRaises(RuntimeError):
                    lab.score(fixtures,observed)
        with self.assertRaisesRegex(RuntimeError,'incomplet'):
            lab.score(fixtures,[])
        observed=capture(fixtures)
        observed[0]['passed']=False
        result=lab.score(fixtures,observed)
        self.assertEqual(result['status'],'unavailable')
        self.assertIsNone(result['metrics'])

    def test_facade_dependencies_and_inputs_only_browser_payload(self):
        fixtures=lab.catalogue(300,42)
        with patch.object(benchmarks,'score',wraps=benchmarks.score) as score:
            with patch.object(verifier,'browser_results',return_value=capture(fixtures)) as browser:
                result=lab.evaluate({'name':'audit_catalogue.html','content':'<p>fixture</p>'},lab.PROFILE,300,42,True)
                self.assertEqual(result['status'],'passed')
                browser.assert_called_once_with('<p>fixture</p>',
                    [{'name':f['name'],'input':f['input']} for f in fixtures],
                    image=lab.IMAGE,mode='laboratory')
            score.assert_called_once()
        self.assertEqual(result['fixture_sha256'],lab.digest(lab.encode(fixtures)))
        self.assertEqual(result['sha256'],lab.digest('<p>fixture</p>'))

    def test_disabled_or_oversized_product_never_executes_browser(self):
        with patch.object(verifier,'browser_results') as browser:
            for enabled,content in ((False,'<p>fixture</p>'),(True,'x'*(verifier.MAX_BYTES+1))):
                result=lab.evaluate({'name':'audit_catalogue.html','content':content},lab.PROFILE,300,42,enabled)
                self.assertEqual(result['status'],'unavailable')
                self.assertIsNone(result['metrics'])
            browser.assert_not_called()


if __name__=='__main__':
    unittest.main()
