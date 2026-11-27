"""Functional assertion regression contracts through the historical verifier."""
import hashlib
import json
import unittest
from unittest.mock import patch

import verification as v
from departments import functional_checks as checks


class FunctionalDepartmentTests(unittest.TestCase):
    def run_spec(self,name,content,spec,enabled=False):
        return v.run(name,content,json.dumps(spec),enabled)

    def test_strict_json_duplicate_nested_and_nonfinite(self):
        for raw in ('{"a":{"x":1,"x":2}}','{"a":Infinity}','{"a":-Infinity}','{"a":1e999}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    v.decode(raw)
        self.assertEqual(v.decode('{"x":1.25,"y":true}'),{'x':1.25,'y':True})

    def test_json_paths_and_type_sensitive_assertions(self):
        spec={'checks':[{'op':'equals','path':['a',0],'expected':True},
                        {'op':'equals','path':['a',1],'expected':1},
                        {'op':'equals','path':['a',True],'expected':1},
                        {'op':'length','path':['a'],'expected':2}]}
        result=self.run_spec('x.json','{"a":[1,true]}',spec)
        self.assertEqual(result['status'],'failed')
        self.assertEqual([x['passed'] for x in result['checks']],[False,False,False,True])
        self.assertIn('Chemin JSON inaccessible',result['checks'][2]['error'])
        with self.assertRaisesRegex(ValueError,'Chemin JSON invalide'):
            v.pointer({},['x']*13)

    def test_csv_decimal_filter_bom_and_delimiter(self):
        data='\ufeffid;net;currency\nA;0.10;EUR\nB;0.20;EUR\nC;9.99;USD\n'
        spec={'delimiter':';','checks':[
            {'op':'columns','expected':['id','net','currency']},
            {'op':'sum','column':'net','where':{'currency':'EUR'},'expected':'0.30'},
            {'op':'unique','column':'id','expected':True},
            {'op':'cell','column':'net','where':{'id':'B'},'row':0,'expected':'0.20'}]}
        result=self.run_spec('x.CSV',data,spec)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['checks'][1]['actual'],'"0.30"')
        self.assertEqual(result['sha256'],hashlib.sha256(data.encode()).hexdigest())

    def test_csv_assertion_errors_are_local_and_bounded(self):
        spec={'checks':[{'op':'sum','column':'net','where':{'id':'missing'},'expected':'0'},
                        {'op':'cell','column':'net','row':99,'expected':'1'},
                        {'op':'row_count','expected':1}]}
        result=self.run_spec('x.csv','id,net\nA,1\n',spec)
        self.assertEqual(result['status'],'failed')
        self.assertEqual([x['passed'] for x in result['checks']],[False,False,True])
        self.assertIn('Aucune ligne sélectionnée',result['checks'][0]['error'])
        self.assertIn('Entier hors limites',result['checks'][1]['error'])
        self.assertEqual(self.run_spec('x.csv','id,net\nA,1',{'checks':[]})['status'],'invalid')
        self.assertEqual(self.run_spec('x.csv','id,net\nA,1',{'checks':[{}]*21})['status'],'invalid')

    def test_html_protocol_validates_before_browser(self):
        valid={'cases':[{'name':'fixture','steps':[{'op':'visible','selector':'#out'}]}]}
        with patch.object(v,'browser_results') as browser:
            self.assertEqual(self.run_spec('x.html','<p>fixture</p>',valid)['status'],'unavailable')
            for steps in ([{'op':'click','selector':'#out'}],
                          [{'op':'evaluate','selector':'#out','value':'1'}],
                          [{'op':'visible','selector':'#out >> text=fixture'}],
                          [{'op':'visible','selector':'#out'}]*13):
                invalid={'cases':[{'name':'fixture','steps':steps}]}
                self.assertEqual(self.run_spec('x.html','<p>fixture</p>',invalid,True)['status'],'invalid')
            browser.assert_not_called()

    def test_legacy_callbacks_and_browser_boundary(self):
        spec={'checks':[{'op':'equals','expected':2}]}
        with patch.object(v,'decode',return_value=2) as decode:
            self.assertTrue(v.data_results('x.json','fixture',spec)[0]['passed'])
            decode.assert_called_once_with('fixture')
        with patch.object(v,'number',wraps=v.number) as number:
            self.assertTrue(v.data_results('x.csv','net\n1\n',{'checks':[{'op':'sum','column':'net','expected':'1'}]})[0]['passed'])
            self.assertEqual(number.call_count,3)
        cases=[{'name':'fixture','steps':[{'op':'visible','selector':'p'}]}]
        with patch.object(v,'browser_results',return_value=[{'name':'fixture','passed':True}]) as browser:
            result=self.run_spec('x.html','<p>fixture</p>',{'cases':cases},True)
            self.assertEqual(result['status'],'passed')
            browser.assert_called_once_with('<p>fixture</p>',cases)

    def test_no_process_or_network_for_data_assertions(self):
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('process forbidden')) as proc:
            result=self.run_spec('x.json','{"items":[1,2]}',{'checks':[{'op':'length','path':['items'],'expected':2}]})
            self.assertEqual(result['status'],'passed')
            proc.assert_not_called()
        self.assertEqual(checks.integer(1,0,2),1)
        self.assertEqual(checks.string('fixture'),'fixture')


if __name__=='__main__':
    unittest.main()
