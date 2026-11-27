"""Local acquisition preview rendering and fictional journey examples.
No storage, network, collection, payment or publication capability.
"""

def text(value, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError('Texte de préparation invalide')
    return value.strip()


def demo(payload):
    """Fictional journey, no product execution, no observation and no stored lead."""
    return {'classification':'synthetic_example','offer_id':payload['offer_id'],
            'snapshot_sha256':payload['snapshot_sha256'],
            'examples':[{'intent':'interest','qualified':False,'reason':'simple interest'},
                        {'intent':'demo_request','qualified':True,'reason':'voluntary demo request in fictional target segment'},
                        {'intent':'purchase_question','qualified':False,'reason':'not a paid order'}],
            'real_observations':0,'paid_orders':0}


def page(payload,*,html):
    e = lambda v: html.escape(str(v), quote=True)
    price = payload['price_cents']
    return ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; form-action \'none\'; base-uri \'none\'">'
        '<title>Brouillon commercial</title><style>'
        'body{font:17px system-ui,sans-serif;max-width:800px;margin:40px auto;padding:20px;color:#183040}'
        'header{background:#eef2f5;padding:16px;border-radius:8px}section{margin:24px 0}'
        'button{padding:10px}p{white-space:pre-wrap;overflow-wrap:anywhere}</style></head>'
        '<body><header><strong>APERÇU INTERNE — NON PUBLIÉ</strong>'
        '<p>Aucun achat, contact ou enregistrement de données possible.</p></header>'
        '<main><h1>'+e(payload['title'])+'</h1><section><h2>Proposition à valider</h2><p>'
        +e(payload['offer'])+'</p><h2>Livrables envisagés</h2><p>'
        +e(payload['deliverables'])+'</p><h2>Prix indicatif non validé</h2><p>'
        +e(f'{price//100},{price%100:02d} EUR')+'</p><h2>Limites</h2><p>'
        +e(payload['limitations'])+'</p><h2>Réserves de préparation</h2><p>'+e(payload['risks'])+'</p></section><section><h2>Parcours fictif</h2>'
        '<p>Exemple illustratif : un visiteur manifeste son intérêt ou demande une démonstration. '
        'Ces actions ne constituent ni commande ni preuve de demande.</p>'
        '<button disabled>Je suis intéressé</button> <button disabled>Demander une démonstration</button>'
        '</section></main></body></html>')
