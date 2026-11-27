"""Pure multichannel rendering contracts, no external services."""
import unittest
from unittest.mock import patch

import marketing_templates as templates
from departments import marketing_content as content


class MarketingContentTests(unittest.TestCase):
    def render(self,*args):
        return templates.render(*(args or (12345,300,42,0,0)))

    def test_registry_and_channel_shape_unchanged(self):
        self.assertEqual(templates.REVISION,1)
        self.assertEqual(templates.PROFILE,'catalogue-v1')
        self.assertEqual(templates.LIMIT,'Brouillon de communication interne; aucune publication ni preuve de demande.')
        result=self.render()
        self.assertEqual(set(result),{'landing','youtube','social','media_policy'})
        self.assertEqual(set(result['landing']),{'title','summary','evidence','limitations','price','cta'})
        self.assertEqual(set(result['youtube']),{'title','description','storyboard'})
        self.assertEqual(set(result['social']),{'text'})
        self.assertEqual(result,content.render(12345,300,42,0,0))

    def test_exact_facts_repeated_without_rounding_or_inflation(self):
        result=self.render(12345,300,37,2,5)
        evidence='Lors d’un test historique sur 300 lignes synthétiques, le laboratoire a relevé 37 alertes correctes, 2 alertes incorrectes et 5 alertes manquées.'
        self.assertEqual(result['landing']['evidence'],evidence)
        self.assertIn(evidence,result['youtube']['description'])
        self.assertEqual(result['youtube']['storyboard'][2]['voice'],evidence)
        self.assertIn(evidence,result['social']['text'])

    def test_indicative_euro_price_exact(self):
        for cents,expected in ((1,'0,01'),(99,'0,99'),(100,'1,00'),(12345,'123,45'),(100000000,'1000000,00')):
            with self.subTest(cents=cents):
                self.assertEqual(self.render(cents,300,42,0,0)['landing']['price'],
                                 'Prix indicatif non validé : '+expected+' €')

    def test_storyboard_order_and_fixed_durations(self):
        result=self.render()
        scenes=result['youtube']['storyboard']
        self.assertEqual([x['seconds'] for x in scenes],[8,12,12,10])
        self.assertEqual(sum(x['seconds'] for x in scenes),42)
        self.assertTrue(all(set(x)=={'seconds','visual','voice'} for x in scenes))
        self.assertEqual(scenes[1]['voice'],result['landing']['summary'])
        self.assertEqual(scenes[2]['voice'],result['landing']['evidence'])
        self.assertEqual(scenes[3]['voice'],result['landing']['limitations']+' '+result['landing']['cta'])

    def test_synthetic_disclosures_and_inactive_cta(self):
        result=self.render()
        landing=result['landing']
        limits='Ce résultat est limité au jeu de données testé. Les performances sur vos données et la demande commerciale ne sont pas validées.'
        self.assertEqual(landing['limitations'],limits)
        self.assertIn(limits,result['youtube']['description'])
        self.assertIn(limits,result['social']['text'])
        self.assertIn(limits,result['youtube']['storyboard'][-1]['voice'])
        self.assertIn('non actif',landing['cta'])
        self.assertIn('Aucun achat ou lien de collecte actif.',result['youtube']['description'])
        self.assertIn('démonstration synthétique',result['youtube']['title'])

    def test_no_media_creation_customer_data_or_music_supplied(self):
        policy=self.render()['media_policy']
        self.assertEqual(policy,{'generated_video':False,'customer_data':False,
                                 'assets':'illustrations synthétiques uniquement',
                                 'music':'aucune musique fournie; vérifier les droits avant diffusion'})

    def test_deterministic_fresh_payloads_and_legacy_callback(self):
        first=self.render()
        second=self.render()
        self.assertEqual(first,second)
        first['youtube']['storyboard'][0]['voice']='changed'
        first['landing']['price']='changed'
        self.assertEqual(self.render(),second)
        with patch.object(content,'render',return_value={'fixture':True}) as render:
            self.assertEqual(self.render(),{'fixture':True})
            render.assert_called_once_with(12345,300,42,0,0)


if __name__=='__main__':
    unittest.main()
