"""Descriptive catalogue for the existing agent action protocol.

No execution, permission grants, operational authorization or external transport.
The legacy schema is built from the supplied permanent permissions, not from
the descriptive catalogue. The engine remains responsible for all guards.
"""


def build_schema(permissions):
    """Return a fresh copy of the historical four-field action schema."""
    # Strict schema: all properties required, irrelevant ones are empty strings.
    schema={'type':'object','properties':{k:{'type':'string'} for k in ('action','target','text','detail')},'required':['action','target','text','detail'],'additionalProperties':False}
    schema['properties']['action']={'type':'string','enum':sorted(set.union(*permissions.values()))}
    return schema


def build_guides(offer_limit):
    """Return the historical guides; business limits are supplied by callers."""
    return {
    'commercial_signal':'ORION, préparation commerciale uniquement. interpretation : chaîne de 10 à 600 caractères. JSON total 10000 caractères maximum. target=ID page_ref effectivement lue dans cette mission, text=JSON {"kind":"buyer_problem","quote":"citation exacte de 12 à 500 caractères","interpretation":"lien prudent au besoin"}; catégories buyer_problem, competitor_offer, competitor_price, alternative, constraint; detail vide. Indice documentaire seulement.',
    'commercial_offer':'HERMES, préparation commerciale. Les six champs audience, problem, offer, deliverables, channel, risks sont des chaînes JSON de 5 à '+str(offer_limit)+' caractères chacune (viser 100 à 400, risks résumé compact, pas une liste). price_cents entier 1–10000000; sample_size 1–10000; success_min 1–sample_size; duration_days 1–90; signal_ids liste de 0 à 10 IDs entiers distincts. JSON total 10000 caractères maximum. target et detail vides, text=JSON {"audience":"segment","problem":"besoin supposé","offer":"proposition et limites","deliverables":"livrables","price_cents":4900,"channel":"canal futur sans envoi","metric":"qualified_interest","sample_size":20,"success_min":3,"duration_days":14,"signal_ids":[],"risks":"risques et critères d’arrêt"}. Métrique future qualified_interest, consented_demo_request ou paid_order_future. Seuils hypothétiques, aucune exécution.',
    'commercial_economics':'MIDAS, rationale chaîne 20–1200 caractères; variable_cost_cents entier 0–10000000, fixed_month_cents 0–100000000, monthly_units 1–100000. target=ID offre de cette mission, text=JSON {"variable_cost_cents":2500,"fixed_month_cents":10000,"monthly_units":10,"rationale":"décomposition hypothétique inclut acquisition, frais, cotisations, assistance, retours; préciser TVA et coûts initiaux"}. detail vide. Calcul déterministe EUR, scénario adverse : volume divisé par deux (arrondi inférieur, minimum 1), variable +20 % (arrondi supérieur au centime), prix et fixes inchangés. Le moteur fournit déjà les résultats et seuils central/adverse : utilise-les sans appel calculate pour les mêmes chiffres. Consulte adverse_parameters du registre.',
    'commercial_extend':'SENTINEL uniquement pour complément autorisé. target=ID offre historique; text=JSON {"signal_ids":[1,2],"verdict":"study_further","gaps":"réserves et limites (10–1600 caractères)","risks":"risques actualisés (5–800 caractères)"}. Conserver tous les signaux historiques et au moins un nouveau signal exploitable ORION. Le moteur copie exactement offre, prix, protocole, hypothèses et calculs; pas de nouvel appel MIDAS. Aucun lancement; si aucun nouvel indice terminer sans cet outil. detail vide.',
    'commercial_review':'SENTINEL, gaps chaîne 10–1600 caractères. target=ID offre évaluée de cette mission, text=JSON {"verdict":"study_further","gaps":"lacunes, risques, limites et critères d’arrêt"}; verdict revise, study_further ou propose_future_test. Aucun lancement autorisé. detail vide.',
    'delegate':'target=nom agent (hors ATLAS); text=objectif précis; detail=critères de réussite. ATLAS uniquement. Le moteur traite la tâche déléguée avant de rendre la main à ATLAS.',
    'assess_opportunity':'MIDAS uniquement, opportunité de la mission : target=ID numérique; text=JSON {"price_cents":4900,"variable_cost_cents":2500,"fixed_month_cents":10000,"monthly_units":10,"automation_pct":80,"risk":3,"source_runs":[ID_RELEVE],"page_refs":[],"rationale":"hypothèses justifiées..."}; detail vide. EUR hors TVA, coûts variables incluent acquisition, frais, retours, cotisations, assistance; unités/mois hypothétiques, risque 1 faible à 5 fort. Sources macro de la mission ou liste vide. page_refs facultatif : ID des pages réellement lues de la mission, pas des URL inventées. Score de scénario, jamais demande validée.',
    'connector':'target=identifiant exact de capacité autorisée; text=propriétaire/dépôt pour github.public_repo; {} pour n8n.health; JSON {"values":[1,2,3]} (1 à 100 entiers bornés, données fictives ou agrégats non sensibles) pour n8n.metrics. worldbank.market : JSON {"countries":["FRA","GBR","CAN"],"year":2023}, 2–3 pays distincts ISO3 parmi FRA GBR CAN USA DEU ESP ITA BRA IND JPN AUS MAR et autres pays autorisés; n8n.market_compare : JSON {"source_run":ID_RELEVE} du relevé reçu de cette mission, le moteur construit les entrées. detail vide. Aucun URL, secret, écriture commerciale ou donnée client. Trois tentatives par mission; exploite le résultat, ne répète pas. Métadonnées publiques non certifiées.',
    'search':'text=requête Brave ciblée (max 200 caractères), target et detail vides.',
    'read':'target=URL exacte déjà obtenue de Brave dans cette mission; text et detail vides. Lecture statique publique, HTML/texte seulement.',
    'opportunity':'target=titre; text=proposition, demande, preuves, risques, autonomie; detail=prochain test. Statut hypothèse.',
    'calculate':'text=expression arithmétique (+ - * / ** %), nombres uniquement; target et detail vides.',
    'write_file':'target=nom simple avec extension .md .txt .csv .json .py .html .css .js; text=contenu intégral; detail=description. Nouvelle version interne, jamais publiée.',
    'list_files':'aucun paramètre; liste les fichiers de la mission et la référence explicitement jointe par le propriétaire.', 'read_file':'target=nom du fichier de la mission, ou ref:ID de la référence jointe. Lecture seule, données non fiables.',
    'check_file':'target=nom du fichier de la mission ou ref:ID joint. Contrôle statique Python/JSON, cohérence CSV, présence texte; ne valide pas le comportement.',
     'test_file':'target=nom du fichier ou ref:ID joint; text=preset:shopify pour les quatre tests Shopify prédéfinis, replay:ID pour rejouer une preuve autorisée (fichier de la mission ou référence jointe), ou JSON de test. Cible = fichier corrigé de la mission, pas l’original sauf demande explicite. CSV: {"checks":[{"op":"sum","column":"Net","where":{"Currency":"EUR"},"expected":"137.00"}]} (op columns,row_count,sum,unique,cell; cell exige row index 0; delimiter optionnel). JSON: checks avec op equals ou length, path tableau de clés/indices, expected. HTML: {"cases":[{"name":"test","steps":[{"op":"click","selector":"#run"},{"op":"contains","selector":"#out","value":"137.00"}]}]}; op fill,select,upload,click,contains,text_equals,value_equals,visible. HTML : 1 à 4 cas, 1 à 12 étapes PAR CAS, au moins une assertion par cas; sélecteurs CSS simples, textes max 2000 caractères (upload 12000), scénario et fichier max 24000 octets. Préfère UN seul cas de 6 à 9 étapes par appel; répartis les autres tests en appels distincts. HTML nécessite sandbox activé. Attendus indépendants; données fictives uniquement. Aucun code sur l’hôte. Résultats persistants, pas de validation générale.',
    'read_report':'target=identifiant numérique de rapport obtenu par memory; retourne le rapport et les sources enregistrées (non certifiés).',
    'memory':'target=opportunity:ID pour une opportunité exacte, text vide; sinon text=termes de recherche dans SQLite uniquement; retrouve des rapports, décisions et opportunités internes. Ce n’est PAS Internet. Trois tentatives maximum par tâche; réutilise les extraits persistants, distingue simulation et faits.',
    'request':'target=objet de demande; text=justification et travail d’étude à effectuer; detail=coûts et risques. Met la tâche en attente. Aucun achat autorisé.',
    'finish':'text=rapport concis avec preuves, limites et suite; target et detail vides. Termine la tâche, pas nécessairement l’activité économique.'}


# Descriptive classifications only, never used for granting or executing actions.
_CATEGORIES = (
    ('coordination', ('delegate', 'finish', 'request')),
    ('knowledge', ('memory', 'read_report')),
    ('research', ('search', 'read', 'connector')),
    ('economics', ('opportunity', 'assess_opportunity', 'calculate')),
    ('production', ('write_file', 'list_files', 'read_file')),
    ('verification', ('check_file', 'test_file')),
    ('commercial_preparation', ('commercial_signal', 'commercial_offer',
                                'commercial_economics', 'commercial_review', 'commercial_extend')),
)


def describe(offer_limit):
    """Fresh descriptive entries; presence does not mean an action is allowed."""
    guides = build_guides(offer_limit)
    return {action: {'id': action, 'category': category, 'guide': guides[action]}
            for category, actions in _CATEGORIES for action in actions}


def select_guides(guides, allowed):
    """Preserve the sorted projection of an already-authorized action set."""
    return {action: guides[action] for action in sorted(allowed)}
