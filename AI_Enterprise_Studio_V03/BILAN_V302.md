# Bilan candidat V3.0.2 — intégration opérationnelle du campus

## Statut et références
Ce document ne constitue ni une livraison ni une autorisation de fusion ou de mise en service. Branche : `feature/v3.0.2-campus-operational`, PR #31, base `39d8b5d215bde287968b13c853def6675957bf05`. Le moteur annonce toujours 3.0.0 ; V3.0.2 désigne le cycle d'intégration. Le SHA exact de livraison sera déterminé après validation du dernier commit et décision de fusion. Aucun appel métier payant effectué pendant cette préparation.

| Périmètre | État à la rédaction |
|---|---|
| O01 — accès opérationnel et aperçu séparés | Validé en CI précédentes |
| O02 — départements, preuves, économie et marketing interne | Validé en CI précédentes |
| O03 — console et autorisations propriétaire | Validé, CI 45873857610 |
| O04 — charge, expérience, mobilisation, incidents, amélioration | Validé, CI 45891834011 |
| O05.1 — inventaire | Commit 80a8a16c, CI 45892267597 en cours à la rédaction |
| O05.2 — procédure Git | Commit 3fccfdbc, non rattaché à la rédaction |
| O05.3 — bilan | Candidat hors branche ; CI finale requise |
| Installation Windows réelle et sauvegarde/restauration réelle | Non effectuées |
| Fusion et démarrage opérationnel | Non autorisés par ce document |

## Résultats et limites
7 bâtiments, 37 étages, 185 équipements uniques, 135 associés à au moins un module, 50 non associés. 73,0 % représente uniquement le raccordement ; les preuves, consultations, préparations internes et simulations ne constituent ni une vente réelle ni un degré d'autonomie. Voir CAMPUS_CAPABILITIES.md (inventaire exhaustif, 17 P1, 24 P2, 9 P3). Le comparatif Git du candidat O05.2 contre la base contient 21 commits, 36 fichiers tous dans V03, aucune suppression ; le présent bilan ajoute un fichier et modifie deux documents, à recontrôler sur le commit final. Aucun changement de schéma exigé par O05, aucune hausse de plafond ou nouvelle permission. Ne pas affirmer que la version est installée localement.

## Conditions de décision de livraison
- Confirmer le SHA de la PR, son état et l'absence de divergence avec main. Vérifier la liste complète des fichiers, l'absence de données privées suivies parmi les modifications, et la préservation V01/V02.
- Confirmer le succès de tous les jobs CI du SHA candidat final, notamment Python, JavaScript, les deux parcours Chromium, préservation V2, migration isolée, sandbox HTML et laboratoire, n8n et World Bank. La disponibilité publique n'est pas une preuve de disponibilité future. Les captures de CI utilisent des fixtures ; ne pas les assimiler à une inspection de l'installation du propriétaire.
- Relever le SHA livré sur main après fusion explicitement autorisée ; vérifier la CI correspondante. Ne jamais substituer le SHA d'une PR brouillon.
- Suivre DEPLOIEMENT_GIT_V302.md : arrêt complet, sauvegarde privée vérifiée, intégrité SQLite, fast-forward uniquement, vérification des données, aperçu original et validation locale avant mise en service. Un point de réanalyse OneDrive peut bloquer la copie : arrêter et examiner, ne pas désactiver le garde.
- Distinguer validation technique de démarrage du moteur, qui peut reprendre les autorisations périodiques. Repli après nouvelles écritures uniquement avec rapprochement des registres.
- Conserver la version précédente et toutes les sauvegardes privées ; aucun ZIP requis pour la V03 suivie.

## Suite métier proposée
Prioriser le socle conformité/droits et registre d'engagements ; outils internes évaluables et réutilisables en produits ; parcours commande/paiement/livraison ; marketing média/publication autorisée ; service client ; académie. Les comptes et crédits restent sous contrôle du propriétaire. Chaque intégration externe exige une politique de coût, un état de test distinct du réel, permissions minimales, idempotence, journalisation, arrêt et rapprochement. Les 50 postes non raccordés restent une feuille de route, non un objectif de remplissage artificiel. Aucun secteur imposé. Aucun revenu réel déduit des signaux TEST. Formation autonome, mobilisation dédiée et autonomie commerciale complète restent à développer.
