"""Macroeconomic normalization contracts, using only synthetic data."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import intelligence as intel
from departments import macroeconomic


class MacroeconomicTests(unittest.TestCase):
    def setUp(self):
        self.spec={'countries':['FRA','GBR'],'year':2023}
        self.rows=[
            self.row('GBR','IT.NET.USER.ZS',90.125),
            self.row('FRA','SP.POP.TOTL',68000000),
            self.row('GBR','SP.POP.TOTL',67000000),
            self.row('FRA','IT.NET.USER.ZS',85.555),
            self.row('FRA','NY.GDP.PCAP.CD',40000.25),
        ]

    @staticmethod
    def row(country,indicator,value,year='2023'):
        return {'countryiso3code':country,'indicator':{'id':indicator},
                'date':year,'value':value}

    def raw(self,rows=None,**meta):
        rows=self.rows if rows is None else rows
        return json.dumps([{'page':1,'pages':1,'total':len(rows),
                           'lastupdated':'2025-01-01',**meta},rows]).encode()

    def normalize(self,rows=None,**meta):
        return intel.parse(self.raw(rows,**meta),self.spec)

    def test_order_units_missing_observations_and_limit(self):
        snapshot=self.normalize()
        self.assertEqual(snapshot['countries'],self.spec['countries'])
        self.assertEqual(snapshot['year'],2023)
        self.assertEqual(snapshot['last_updated'],'2025-01-01')
        self.assertEqual(snapshot['limit'],intel.LIMIT)
        self.assertEqual([(x['country'],x['indicator'],x['unit']) for x in snapshot['observations']],
                         [(country,key,value[1]) for country in self.spec['countries']
                          for key,value in intel.INDICATORS.items()])
        self.assertEqual([x['value'] for x in snapshot['observations']],
                         [68000000,85.555,40000.25,67000000,90.125,None])
        direct=macroeconomic.parse(self.raw(),self.spec,decode=intel.decode,
            MAX_BYTES=intel.MAX_BYTES,INDICATORS=intel.INDICATORS,LIMIT=intel.LIMIT)
        self.assertEqual(direct,snapshot)

    def test_null_is_not_zero_and_update_format(self):
        snapshot=self.normalize([self.row('FRA','SP.POP.TOTL',0)],lastupdated='unknown')
        self.assertIsNone(snapshot['last_updated'])
        self.assertEqual(snapshot['observations'][0]['value'],0)
        self.assertTrue(all(r['value'] is None for r in snapshot['observations'][1:]))
        with self.assertRaisesRegex(ValueError,'Aucune observation disponible'):
            self.normalize([self.row('FRA','SP.POP.TOTL',None)])

    def test_pagination_and_response_bound(self):
        for meta in ({'page':2},{'pages':2},{'total':6},{'page':'bad'}):
            with self.subTest(meta=meta), self.assertRaisesRegex(ValueError,'Pagination'):
                self.normalize(**meta)
        with self.assertRaisesRegex(ValueError,'trop volumineuse'):
            intel.parse(b' '* (intel.MAX_BYTES+1),self.spec)

    def test_rejects_wrong_identity_or_duplicate(self):
        for row in (self.row('USA','SP.POP.TOTL',1),
                    self.row('FRA','unknown',1),
                    self.row('FRA','SP.POP.TOTL',1,'2022'),
                    self.rows[0]):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError,'doublon inattendu'):
                self.normalize(self.rows+[row])

    def test_strict_json_and_invalid_value_types(self):
        for raw,reason in [(b'{"x":1,"x":2}','Clé JSON dupliquée'),
                           (b'[NaN]','Nombre non fini')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError,reason):
                intel.parse(raw,self.spec)
        for value in (True,'12',-1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'Valeur statistique invalide'):
                self.normalize([self.row('FRA','SP.POP.TOTL',value)])

    def test_statistical_boundaries(self):
        for indicator,value,reason in [
            ('SP.POP.TOTL',1.5,'Population invalide'),
            ('SP.POP.TOTL',2000000001,'Population invalide'),
            ('IT.NET.USER.ZS',100.01,'Pourcentage invalide'),
            ('NY.GDP.PCAP.CD',2000001,'PIB par habitant invalide')]:
            with self.subTest(indicator=indicator,value=value), self.assertRaisesRegex(ValueError,reason):
                self.normalize([self.row('FRA',indicator,value)])
        valid=[self.row('FRA','SP.POP.TOTL',2000000000),
               self.row('FRA','IT.NET.USER.ZS',100),
               self.row('FRA','NY.GDP.PCAP.CD',2000000)]
        self.assertEqual([x['value'] for x in self.normalize(valid)['observations'][:3]],
                         [2000000000,100,2000000])

    def test_comparison_rounding_and_exclusion_of_missing_data(self):
        snapshot=self.normalize()
        original=deepcopy(snapshot)
        self.assertEqual(intel.compare_rows(snapshot),[
            {'country':'FRA','population':68000000,'internet_bp':8556},
            {'country':'GBR','population':67000000,'internet_bp':9013}])
        self.assertTrue(intel.comparable(snapshot))
        self.assertEqual(snapshot,original)
        snapshot['observations'][4]['value']=None
        self.assertFalse(intel.comparable(snapshot))
        self.assertEqual(len(intel.compare_rows(snapshot)),1)

    def test_live_facade_dependencies_preserved(self):
        with patch.object(intel,'decode',wraps=intel.decode) as decode:
            self.normalize()
            decode.assert_called_once_with(self.raw())
        with patch.object(intel,'LIMIT','fixture limit'):
            self.assertEqual(self.normalize()['limit'],'fixture limit')
        with patch.object(intel,'MAX_BYTES',1):
            with self.assertRaisesRegex(ValueError,'trop volumineuse'):
                self.normalize()


if __name__=='__main__':
    unittest.main()
