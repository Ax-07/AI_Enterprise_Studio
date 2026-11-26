# O02.6 — Inventaire des équipements non raccordés

Référence analysée : `adf18ecf97b23e75675b7d2d8d4bdea762888bb2`. Source : `interface/live-layout.js` et union des clés `stations` et `native` dans `interface/live-modules.js`. 37 services, 185 équipements ; 133 associés à un module, 52 sans association. Ce n'est pas un taux d'autonomie ni une validation fonctionnelle. Les 133 accès associés peuvent eux-mêmes rester partiels (par exemple statistiques TEST, exports, média et vente non autorisés).

## Classification proposée

| Code | Nature | Nombre |
|---|---|---:|
| R | Réutilisation / projection | 7 |
| E | Export à sécuriser | 10 |
| N | Nouveau outil interne | 24 |
| X | Intégration ou opération externe | 8 |
| D | Maquette / besoin à requalifier | 3 |

P1 : dépendance prioritaire pour les revenus réels et la maîtrise des risques ; P2 : capacité opérationnelle et pilotage ; P3 : confort, archivage ou extension conditionnelle. Les priorités ne constituent ni budget ni autorisation d'action externe. Les catégories sont des choix d'architecture proposés, pas une preuve d'absence exhaustive de toute fonction dans le dépôt.

## Inventaire exhaustif des 52 postes

### ATLAS — 31/45 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `LOBBY:station:2` | Espace visiteurs | X | P1 | Parcours d'acquisition public distinct du campus local ; consentement, sécurité, validation et canal autorisé. Le moteur acquisition ne fournit aujourd'hui qu'une préparation interne et TEST. |
| `LOBBY:station:4` | Informations | N | P3 | Fiche institutionnelle versionnée et validée, distincte d'une vitrine publique. Réutiliser les informations de configuration et les offres internes sans inventer de société immatriculée. |
| `MEETING:station:4` | Compte rendu | R | P2 | Rapports et missions déjà lisibles via report/memory ; définir un compte rendu lié à une mission réelle et téléchargement borné ; ne pas fabriquer de réunion. |
| `NOTIFICATIONS:station:3` | Synchronisation | D | P3 | Import d'instantané de maquette à écarter en exploitation sauf besoin démontré ; source, schéma, validation et restauration requis. |
| `NOTIFICATIONS:station:4` | Export des notifications | E | P2 | Exporter les décisions et notifications projetées, sans secrets, avec horodatage et schéma. |
| `PEOPLE17:station:0` | Besoins | N | P2 | Cartographier besoins de compétences à partir des tâches bloquées, permissions et rôles existants ; critères explicites et contrôle ATLAS. |
| `PEOPLE17:station:4` | Mobilisation | N | P2 | Mobilisation et délégation par le moteur existant ; règles de capacité, budget, permissions et autorisation ; aucune création automatique d'identité. |
| `GROUP:station:1` | Quartiers spécialisés | R | P2 | Projeter projets/portfolio et rôles existants ; ajouter une taxonomie sectorielle explicite si absente, sans inférer de filiales réelles. |
| `GROUP:station:3` | Contrat de données | D | P3 | Import de maquette non nécessaire ; si réactivé, valider version et provenance, sans écraser SQLite. |
| `GROUP:station:4` | Rapport du groupe | E | P2 | Rapport consolidé portefeuille/missions/coûts à partir des vues existantes ; données TEST séparées, pas de comptes consolidés certifiés. |
| `EXPAND:station:0` | Plan des étages | R | P3 | Inventaire statique des étages et accès depuis live-layout/live-modules ; distinguer capacité graphique et opérationnelle. |
| `EXPAND:station:1` | Capacité | N | P2 | Modèle de capacité numérique mesurable : files de tâches, coûts, limites de concurrence et ressources techniques. |
| `EXPAND:station:3` | Jalons | N | P2 | Jalons d'expansion explicites, preuves et validations ATLAS/SENTINEL ; pas de croissance automatique. |
| `EXPAND:station:4` | Plan vertical | E | P3 | Export du plan statique et état des raccordements, sans données privées. |

### ORION — 10/15 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `WORLD:station:1` | Europe | R | P2 | Projection par pays européens des sources intelligence.status existantes ; vérifier intégrité, année, unités, absence de données et limites macroéconomiques. |
| `WORLD:station:2` | Amérique du Nord | R | P2 | Même projection pour les pays nord-américains disponibles ; pas de requête réseau à l'ouverture. |
| `WORLD:station:3` | Asie-Pacifique | R | P2 | Même projection pour les pays Asie-Pacifique disponibles ; pas de couverture complète présumée. |
| `OPPORTUNITIES:station:2` | Marchés par secteur | N | P2 | Taxonomie sectorielle et provenance explicite, classement sur hypothèses et non demande vérifiée ; ne pas imposer un secteur unique. |
| `OPPORTUNITIES:station:4` | Dossier des opportunités | E | P2 | Export borné des opportunités et évaluations actuelles ; ne pas prétendre reconstituer tout V2 sans données correspondantes. |

### NEXUS — 19/25 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `PORTFOLIO:station:4` | Export du portefeuille | E | P2 | Export de la projection portfolio et des références d'artefacts, sans contenu confidentiel par défaut. |
| `FULFILL17:station:0` | Commandes | X | P1 | Registre de commandes réelles avec prestataire, statuts idempotents et rapprochement ; les signaux TEST ne sont pas des commandes. |
| `FULFILL17:station:1` | Livraison | X | P1 | Livraison vérifiée de produits/services, preuve de remise et traitement des échecs. |
| `FULFILL17:station:2` | Activations | X | P1 | Activation de droits d'accès ou services après paiement confirmé ; révocation et contrôle des doublons. |
| `FULFILL17:station:3` | Suivi service | N | P1 | Suivi interne des engagements, incidents et niveaux de service ; dépend du registre réel des commandes. |
| `FULFILL17:station:4` | Conformité | N | P1 | Contrôle pré-remise utilisant quality, laboratoire et règles spécifiques au produit ; pas de certification générale. |

### MIDAS — 14/20 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `ECON:station:4` | Rapport financier | E | P2 | Export economy/finance des scénarios et dépenses USD, encaissements EUR séparés ; aucune comptabilité réelle déduite. |
| `INVESTMENTS:station:4` | Rapport d’allocation | E | P3 | Export des hypothèses et décisions enregistrées ; aucune allocation ou performance d'investissement inventée. |
| `BUY17:station:0` | Fournisseurs | N | P2 | Registre fournisseurs, provenance, conditions, risques et statuts de validation ; connecteurs existants distincts des fournisseurs approuvés. |
| `BUY17:station:1` | Abonnements | N | P2 | Registre abonnements et échéances déclarés, devises, coût récurrent et alertes ; pas de débit automatique. |
| `BUY17:station:2` | Comparatifs | N | P2 | Comparaison des offres fournisseurs sur devis ou tarifs datés et vérifiables ; recherche externe sous quota. |
| `BUY17:station:3` | Demandes achat | N | P2 | Demandes d'achat avec budget, contrôle SENTINEL et approbation propriétaire ; achat réel désactivé. |

### HERMES — 31/40 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `SUPPORT17:station:0` | Demandes | X | P1 | Entrées client autorisées, canal de support, minimisation des données, consentement selon contexte ; pas de prospects réels issus des TEST. |
| `SUPPORT17:station:1` | Réclamations | N | P1 | Registre de réclamations lié à commandes et support, règles d'escalade et délais ; ne pas assimiler remboursement déclaré à une demande. |
| `SUPPORT17:station:3` | Satisfaction | N | P2 | Mesure de satisfaction liée aux interactions réelles, taille d'échantillon et distinction TEST. |
| `COMMS:station:0` | Réseau holographique | R | P2 | Flux interne de délégations/événements persistés de campus_live et work, pas de présence ou hologramme inventé. |
| `COMMS:station:4` | Archive des échanges | E | P2 | Export du journal interne autorisé, sans arguments bruts ni secrets, avec limites et provenance. |
| `VIDEO183:station:1` | Génération | X | P1 | Adaptateur vidéo asynchrone, devis et réservations, quotas, validation d'assets, états jobs, annulation et réconciliation ; scénario marketing existant seulement. |
| `VIDEO183:station:2` | Voix & son | X | P1 | Adaptateur voix/audio et règles de licence, consentement vocal et coût ; pas de clonage non autorisé. |
| `VIDEO183:station:3` | Montage | N | P1 | Montage local reproductible sur assets contrôlés, validation format/durée/droits, test sans API. |
| `PUBLISH183:station:3` | Publication | X | P1 | File de publication versionnée, connecteur YouTube/social, permissions, contrôle pré-publication, idempotence et arrêt ; jamais confondre préparation et publication. |

### SENTINEL — 10/15 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `LEGAL17:station:0` | Contrats | N | P1 | Registre des contrats, versions, parties et validations ; revue humaine compétente pour engagements. |
| `LEGAL17:station:1` | Licences | N | P1 | Registre licences, preuves et périmètre d'usage des logiciels et médias ; refus si droits indéterminés. |
| `LEGAL17:station:2` | Confidentialité | N | P1 | Registre traitements, finalités, rétention et contrôle d'accès ; aucune conformité juridique automatique. |
| `LEGAL17:station:3` | Obligations | N | P1 | Registre obligations par activité et juridiction, sources datées et alertes ; validation humaine selon risque. |
| `LEGAL17:station:4` | Validations | N | P1 | Circuit de validations juridiques et exceptions avec preuve, décision propriétaire et expiration ; distinct des décisions génériques. |

### CORE — 18/25 associés

| Identifiant | Poste | Type | Priorité | Travail / dépendance |
|---|---|---|---|---|
| `ACADEMY:station:0` | Simulateur | N | P2 | Banc de scénarios synthétiques et réutilisation des modes simulation/laboratoire, sans coûts externes ni résultat fictif enregistré comme réel. |
| `ACADEMY:station:2` | Atelier pratique | N | P2 | Exercices reproductibles, critères de succès, fixtures et permissions ; aucun apprentissage de modèle présumé. |
| `ACADEMY:station:3` | Bilan pédagogique | N | P2 | Résultats mesurés, comparaison de versions et limites ; réutiliser improvement et laboratory sans confondre entraînement et test. |
| `ACADEMY:station:4` | Archives de formation | E | P3 | Export des futures sessions validées ; dépend du registre pédagogique, aucun historique inventé. |
| `ARCHIVES:station:2` | Archives pédagogiques | N | P3 | Archivage de sessions pédagogiques versionnées avec provenance et empreintes ; dépend d'ACADEMY. |
| `ARCHIVES:station:3` | Données importées | D | P3 | Instantanés externes non nécessaires par défaut ; ingestion en quarantaine et validation de schéma si besoin réel. |
| `ARCHIVES:station:4` | Export des archives | E | P2 | Export borné d'historique missions/rapports, redaction, autorisation et contrôle d'intégrité ; distinct d'une sauvegarde restaurable. |

## Ordre de réalisation recommandé

1. O03 : console propriétaire, budgets et décisions, visibilité des lacunes ; aucun achat ni publication par défaut.
2. O04 : pilotage autonome borné, compétences et mobilité, capacités et journalisation ; réutiliser moteur, planner, periodic et incidents.
3. O05 : valider le campus, distinguer accès, préparation, TEST et réel ; conserver les postes indisponibles si aucune capacité correspondante.
4. Chantiers métier parallèles après protections : conformité/droits et registre d'engagements, parcours client/commandes/paiements/livraison, fournisseurs/abonnements, médias/publication, intelligence sectorielle et académie. Chaque opération externe exige contrat, sandbox/test, politique de coûts, permissions, journal, mécanisme d'arrêt et validation appropriée.

Outils propriétaires à évaluer : gestion des droits/contrôles de livrables, moteur de rapprochement et preuve de livraison, comparateur de marchés sourcé, pipeline média contrôlé, banc d'évaluation. Leur commercialisation est une hypothèse, pas une décision ni une preuve de marché. Ne pas créer de nouveaux agents, modifier le design, simuler des activités ou imposer un secteur économique pour remplir les postes.
