"""Commercial validation boundaries and preserved historical facades."""
import hashlib
import json
import unittest
from unittest.mock import patch

import business as b
import commercial as co
from departments import commercial_validation as cv


class CommercialValidationTests(unittest.TestCase):
    def test_exact_json_fields_without_coercion(self):
        self.assertEqual(co._obj('{"a":1,"b":"x"}',('a','b')),{'a':1,'b':'x'})
        for raw in ('[]','null','{"a":1}','{"a":1,"b":2,"c":3}'):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'Champs requis'):
                co._obj(raw,('a','b'))
        for raw in ('{"a":1,"a":2,"b":3}','{"a":NaN,"b":1}','{"a":Infinity,"b":1}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                co._obj(raw,('a','b'))

    def test_json_size_and_type_limits(self):
        raw=json.dumps({'x':'a'*9991},separators=(',',':'))
        self.assertEqual(len(raw),9999)
        self.assertEqual(co._obj(raw+' ',('x',))['x'],'a'*9991)
        for value in (None,{},raw+'  '):
            with self.subTest(value=type(value)),self.assertRaisesRegex(ValueError,'JSON commercial trop long'):
                co._obj(value,('x',))

    def test_text_trimmed_length_and_no_mutation(self):
        data={'risks':'  abc  '}
        self.assertIsNone(co._text(data,'risks',3,3))
        self.assertEqual(data['risks'],'  abc  ')
        for value in ('ab','abcd','   ',1,True,None):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Texte invalide : risks'):
                co._text({'risks':value},'risks',3,3)

    def test_strict_integer_bounds_for_both_interfaces(self):
        for value in (1,10):
            self.assertIsNone(co._int({'n':value},'n',1,10))
            self.assertEqual(b.integer(value,1,10),value)
        for value in (True,False,1.0,'1',0,11,None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'Valeur invalide : n'):
                    co._int({'n':value},'n',1,10)
                with self.assertRaisesRegex(ValueError,'Entier hors limites'):
                    b.integer(value,1,10)
        self.assertEqual(b.integer(9007199254740991),9007199254740991)
        with self.assertRaises(ValueError):b.integer(9007199254740992)

    def test_ascii_numeric_target_and_historical_leading_zeros(self):
        self.assertEqual(co._id('0001'),1)
        self.assertEqual(co._id('999999999999'),999999999999)
        for value in ('','0','000','-1','+1',' 1','1.0','１２','١','1234567890123'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'ID numérique requis'):
                co._id(value)

    def test_explicit_confirmation_and_exact_owner_fields(self):
        body={'confirm':True,'offer':7}
        self.assertIsNone(b.fields(body,('offer',)))
        self.assertEqual(body,{'confirm':True,'offer':7})
        for value in (None,[],{'offer':7},{'confirm':1,'offer':7},{'confirm':False,'offer':7},
                      {'confirm':True},{**body,'extra':True}):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Confirmation explicite et champs exacts requis'):
                b.fields(value,('offer',))

    def test_opaque_reference_hash_length_and_charset(self):
        for ref in ('A'*16,'Z'*80,'fixture-ref_12345678'):
            expected=hashlib.sha256(ref.encode()).hexdigest()
            self.assertEqual(b.opaque(ref),expected)
            self.assertEqual(len(expected),64)
        for ref in ('A'*15,'A'*81,'person@example.com','é'*20,'A'*16+'\n',None):
            with self.subTest(ref=ref),self.assertRaisesRegex(ValueError,'Référence opaque'):
                b.opaque(ref)

    def test_live_decoder_and_hash_callbacks(self):
        with patch.object(co.intel,'decode',return_value={'x':1}) as decode:
            self.assertEqual(co._obj('fixture',('x',)),{'x':1})
            decode.assert_called_once_with('fixture')
        with patch.object(cv,'opaque',return_value='digest') as opaque:
            self.assertEqual(b.opaque('fixture-ref_12345678'),'digest')
            opaque.assert_called_once_with('fixture-ref_12345678',re=b.re,hashlib=b.hashlib)


if __name__=='__main__':
    unittest.main()
