"""Offline acquisition preview contracts through historical interfaces."""
import html
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

import acquisition as ac
from departments import acquisition_preview as preview


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements=[]
    def handle_starttag(self,tag,attrs):
        self.elements.append((tag,dict(attrs)))


class AcquisitionDepartmentTests(unittest.TestCase):
    def payload(self,**changes):
        return {'title':'Catalogue multilingue','offer':'Audit interne',
                'deliverables':'Rapport local','price_cents':12345,
                'limitations':'Demande non validée','risks':'Prototype',
                'offer_id':7,'snapshot_sha256':'fixture-snapshot',**changes}

    def test_text_strict_limits_and_legacy_strip(self):
        self.assertEqual(ac._text('  exemple  '),'exemple')
        self.assertEqual(ac._text('abc',3),'abc')
        for raw in ('','   ',None,123,'abcd'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError,'Texte de préparation invalide'):
                    ac._text(raw,3)
        self.assertEqual(preview.text('  test  '),'test')

    def test_fictional_examples_are_not_observations(self):
        result=ac.demo(self.payload())
        self.assertEqual(result['classification'],'synthetic_example')
        self.assertEqual(result['offer_id'],7)
        self.assertEqual(result['snapshot_sha256'],'fixture-snapshot')
        self.assertEqual([x['intent'] for x in result['examples']],
                         ['interest','demo_request','purchase_question'])
        self.assertEqual([x['qualified'] for x in result['examples']],[False,True,False])
        self.assertEqual((result['real_observations'],result['paid_orders']),(0,0))

    def test_escape_all_untrusted_fields(self):
        attack='<img src=x onerror="alert(1)">&'
        keys=('title','offer','deliverables','limitations','risks')
        payload=self.payload(**dict.fromkeys(keys,attack))
        rendered=ac._page(payload)
        self.assertEqual(rendered.count(html.escape(attack,quote=True)),len(keys))
        self.assertNotIn(attack,rendered)
        parser=PreviewParser();parser.feed(rendered)
        self.assertNotIn('img',[tag for tag,attrs in parser.elements])

    def test_no_active_controls_or_external_resources(self):
        parser=PreviewParser();parser.feed(ac._page(self.payload()))
        self.assertFalse({'form','script','iframe','input','a','img','link','object'} &
                         {tag for tag,attrs in parser.elements})
        buttons=[attrs for tag,attrs in parser.elements if tag=='button']
        self.assertEqual(len(buttons),2)
        self.assertTrue(all('disabled' in attrs for attrs in buttons))
        csp=next(attrs['content'] for tag,attrs in parser.elements
                 if tag=='meta' and attrs.get('http-equiv')=='Content-Security-Policy')
        for restriction in ("default-src 'none'","form-action 'none'","base-uri 'none'"):
            self.assertIn(restriction,csp)
        self.assertTrue(all(not {'src','href','action','formaction'} & set(attrs)
                            for tag,attrs in parser.elements))

    def test_exact_cent_rendering_and_disclosures(self):
        for cents,expected in ((1,'0,01 EUR'),(100,'1,00 EUR'),(12345,'123,45 EUR'),(100000000,'1000000,00 EUR')):
            with self.subTest(cents=cents):
                rendered=ac._page(self.payload(price_cents=cents))
                self.assertIn(expected,rendered)
                self.assertIn('APERÇU INTERNE — NON PUBLIÉ',rendered)
                self.assertIn('Prix indicatif non validé',rendered)
                self.assertIn('ni commande ni preuve de demande',rendered)

    def test_deterministic_render_and_input_unchanged(self):
        payload=self.payload()
        before=dict(payload)
        self.assertEqual(ac._page(payload),preview.page(payload,html=html))
        self.assertEqual(ac._page(payload),ac._page(payload))
        self.assertEqual(ac.demo(payload),ac.demo(payload))
        self.assertEqual(payload,before)
        self.assertNotIn('fixture-snapshot',ac._page(payload))

    def test_legacy_callbacks_resolved_at_call_time(self):
        payload=self.payload()
        with patch.object(ac.html,'escape',wraps=html.escape) as escape:
            ac._page(payload)
            self.assertEqual(escape.call_count,6)
            self.assertTrue(all(x.kwargs=={'quote':True} for x in escape.call_args_list))
        with patch.object(preview,'demo',return_value={'fixture':True}) as demo:
            self.assertEqual(ac.demo(payload),{'fixture':True})
            demo.assert_called_once_with(payload)


if __name__=='__main__':
    unittest.main()
