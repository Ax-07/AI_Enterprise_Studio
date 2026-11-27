"""Deterministic catalogue marketing copy for internal previews only.
No media creation, external transport or publication authorization.
"""

def render(price_cents,size,tp,fp,fn):
    price=f'{price_cents//100},{price_cents%100:02d} €'
    evidence=f'Lors d’un test historique sur {size} lignes synthétiques, le laboratoire a relevé {tp} alertes correctes, {fp} alertes incorrectes et {fn} alertes manquées.'
    limits='Ce résultat est limité au jeu de données testé. Les performances sur vos données et la demande commerciale ne sont pas validées.'
    title='Audit de catalogues multilingues'
    summary='Vérifiez des exemples de catalogues JSON : SKU, titres et locales. Le prototype vise à signaler les champs manquants, les doublons et les locales absentes.'
    cta='Découvrir le parcours de démonstration (futur canal, non actif).'
    return {
        'landing':{'title':title,'summary':summary,'evidence':evidence,'limitations':limits,
                   'price':'Prix indicatif non validé : '+price,'cta':cta},
        'youtube':{'title':'Audit de catalogues multilingues — démonstration synthétique',
                   'description':summary+' '+evidence+' '+limits+' Aucun achat ou lien de collecte actif.',
                   'storyboard':[
                       {'seconds':8,'visual':'Titre et exemple fictif de catalogue','voice':'Un catalogue multilingue peut comporter des champs manquants ou des doublons.'},
                       {'seconds':12,'visual':'Illustration de lignes JSON fictives, sans données client','voice':summary},
                       {'seconds':12,'visual':'Afficher les résultats historiques avec mention données synthétiques','voice':evidence},
                       {'seconds':10,'visual':'Écran de limites et appel à découvrir la démonstration','voice':limits+' '+cta}]},
        'social':{'text':title+' : '+summary+' '+evidence+' '+limits+' '+cta},
        'media_policy':{'generated_video':False,'customer_data':False,'assets':'illustrations synthétiques uniquement',
                        'music':'aucune musique fournie; vérifier les droits avant diffusion'},
    }
