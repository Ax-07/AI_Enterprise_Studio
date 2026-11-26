# V3.1.0 — Architecture de référence (R01)

Statut : proposition technique pour le cycle de refactoring, sans changement de comportement. Base stable : `e9e8c5ba4e47218bcafa2bc30371efb8636675ab` (V3.0.2, PR #31). CI du candidat 45893273713 : 298 tests Python exécutés et suite complète réussie ; CI main confirmée par le propriétaire. Installation locale fast-forward, sauvegarde vérifiée des 218 fichiers, données et configuration identiques ; aperçu confirmé par le propriétaire, démarrage opérationnel non validé. Le numéro moteur historique reste 3.0.0. Aucun secteur économique imposé.

## Décisions
- Monolithe modulaire Python, SQLite et interface HTML/CSS/JavaScript existants. Pas de framework, de nouveau service réseau, de dépendance payante ni de nouvelle identité agent par défaut.
- Le découpage métier suit les capacités et non les bâtiments : un outil partagé peut servir plusieurs départements. Les 7 bâtiments et 8 agents sont des concepts distincts. Les 37 étages et 185 équipements, dont 135 associés, restent inchangés pendant ce cycle sauf décision spécifique.
- Déplacements incrémentaux avec points d'entrée de compatibilité, petits commits et validation complète. Un déplacement n'est pas une opportunité de modifier une politique, un schéma, une API ou une règle de coût. Les corrections de comportement sont isolées et justifiées.
- Les interfaces ne décident pas des permissions. Une décision propriétaire reste distincte d'une action agent et d'une lecture. Préserver la séparation demo/cloud/TEST/réel et aperçu/opérationnel.
- Une capacité commercialisable doit avoir un noyau indépendant du campus, de la base d'entreprise et des secrets. L'adaptateur interne lui fournit explicitement les ressources nécessaires ; l'interface client éventuelle possède ses propres droits et données.

## Frontières cibles (progressives)
| Couche | Responsabilité | Dépendances autorisées en cible |
|---|---|---|
| core | Contrats, identité agent, règles métier transversales, orchestration | contrats et ports abstraits, pas HTTP ni interface |
| departments | Services métier par capacité | core, contrats d'outils ; pas de dépendance directe entre interfaces de départements |
| tools | Fonctions isolées et catalogue des capacités | contrats minimaux ; pas serveur, campus ou accès implicite aux secrets |
| infrastructure | SQLite, transport fournisseur, connecteurs, runtime, horloge | implémente les ports ; pas de dépendance vers l'interface |
| api | Routes, validation, adaptation des requêtes, réponses | services applicatifs et politiques ; pas de logique de coût dupliquée |
| interface | Campus, état de navigation, composants, historique | API existantes via adaptateurs JS ; aucun secret fournisseur |
| bootstrap | Assemblage explicite, démarrage des workers et configuration | assemble les couches ; seul endroit où l'ensemble est connu |
| tests / docs | contrats, régression, décisions | indépendants du code de production au déploiement |

Ces noms sont des cibles, pas une obligation de déplacer tous les fichiers. Commencer avec quelques modules plats indépendants si nécessaire pour éviter les réexports fragiles. Pas de dossier vide créé uniquement pour respecter l'arborescence.

## Contrats et invariants
1. **Identité et permissions** : conserver identifiants ATLAS, ORION, NEXUS, MIDAS, HERMES, SENTINEL, PROMETHEUS, MNEMOS ; valeurs de ROLES, PERMS et action enum. Pas de droit ajouté. L'autorisation vient du moteur, des limites campagne/mission/période et des décisions existantes, non du catalogue d'outils.
2. **Exécution** : préserver les paramètres action/target/text/detail, erreurs et contrôles de taille, validation du schéma, délégation, plafonds de tâches/tours/appels, prévention des répétitions, journaux et arrêt. L'ordre des contrôles de moteur.execute (permission, fenêtre et campagne avant l'outil) est une référence de non-régression.
3. **Orchestration** : périodique autorise des plans, plans organisent des campagnes, campagnes pilotent les missions ; les gardes et liens inverses restent nécessaires. Extraire ultérieurement contrats de consultation/autorisation sans changer l'ordre des transactions. Pas de nouveau worker automatique.
4. **Coûts** : réservations, dépenses réellement mesurées, inconnues/non rapprochées, plafonds et unités historiques restent identiques. Un appel transport interdit ou non autorisé ne doit pas être déclenché. Aucun double comptage des enveloppes imbriquées.
5. **Données** : conserver donnees/enterprise.sqlite3, config.json, stockage TEST et chemins, identifiants, colonnes et écritures historiques. Transaction et rollback de serveur.db ; s.DB demeure substituable dans les tests. Pas d'initialisation ni de purge métier dans une simple lecture/aperçu. Le démarrage normal garde ses protections de reprise existantes.
6. **API et sécurité** : routes et payloads existants, code HTTP, contrôle local Host/Origin, jetons distincts et validation des tailles, POST_LOCK et protections de concurrence. Ne pas déplacer les contrôles après les effets. Les routes propriétaire/commande restent séparées. Aperçu : aucun POST, aucun jeton de mutation, aucun worker ni service TEST, projections en lecture seule.
7. **Compatibilité** : serveur.py et moteur.py restent des façades appelables, signatures existantes et points de substitution (serveur.DB/config/request, moteur.fetch_page) préservés ou adaptateurs testés. Ne pas capturer les références patchées à l'import ; ne pas dupliquer état global ni verrous. Préserver les lanceurs Windows, chemins d'assets et CSP. Pas de migration générale des tests avant la stabilisation du nouvel assemblage.
8. **Outils** : métadonnées proposées : identifiant stable, version du contrat, schémas entrée/sortie, catégorie, modes permis, effet (lecture/écriture/externe), autorisation, budget, idempotence, preuve/audit, politique d'arrêt. Le registre décrit, l'exécuteur vérifie. Pas de catalogue dynamique qui pourrait accorder des permissions.

## Séquencement
R02 avant tout package : inventaire de l'arbre suivi, politique de sélection commune au build et à l'installation parallèle, métadonnées de livraison explicites, tests de contenu ZIP et copie de sous-modules, exclusions de secrets et liens. R03 : extraction d'une fonction pure et contrats de configuration/données ; R04 : identité et garde de moteur puis exécution, orchestration séparément. R05 : services métier et projections ; R06 : outils isolés ; R07 : API et interface par petites étapes ; R08 : gouvernance/documentation ; R09 : validation et livraison. L'ordre peut être ajusté selon les preuves, pas pour remplir artificiellement des dossiers.

## Portes de validation
Chaque lot : comparaison Git bornée, tests ciblés et suite Python complète, syntaxe JS, smoke Chromium, migrations hors ligne, n8n/World Bank et sandbox/laboratoire selon la CI existante. Tests de contrats supplémentaires avant extraction des zones sensibles, dont refus de commandes en aperçu, permissions, limites budgétaires, comptabilité du registre et reprise d'incidents. Pas de seuil de couverture arbitraire avant mesure. Tester dans des bases temporaires, avec transports payants interdits. Déploiement local séparé, sauvegarde et repli vérifiés, fusion autorisée séparément.
