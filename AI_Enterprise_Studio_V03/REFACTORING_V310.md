# R00 — Registre de dette technique initial et feuille de route V3.1.0

Référence : `e9e8c5ba4e47218bcafa2bc30371efb8636675ab`. Audit statique ciblé, pas d'inventaire exhaustif ni preuve de code mort. Le connecteur permet la lecture des fichiers connus mais ne fournit pas l'arbre complet ; ne supprimer aucun module sur cette base. Les tailles sont en caractères de source, pas des mesures de complexité. Le journal CI 45893273713 indique 298 tests en 22,207 s sur runner CI.

| ID | Observation vérifiée | Risque / ordre |
|---|---|---|
| R00-01 | serveur.py : 58 265 caractères, HTTP, config, init SQLite, appels IA, état et workers ; POST_LOCK partagé avec acquisition_control_loop | séparation après contrats et protections |
| R00-02 | moteur.py : 63 976 caractères ; ROLES/PERMS/SCHEMA, outils, recherche, preuves, contexte, boucle | extractions isolées, ne pas changer les gardes |
| R00-03 | periodic importe planner et autopilot ; ces derniers importent periodic en différé ; portfolio et draft_recovery se référencent | cartographier et découpler par ports, pas de suppression aveugle |
| R00-04 | build_candidate.py et prepare_update.py sélectionnent des fichiers racine et interface/sandbox/n8n ; les nouveaux packages ne sont pas inclus | bloquant avant création des packages |
| R00-05 | build_candidate.py étiquette encore V3.0.0/D08.3 ; serveur annonce 3.0.0 | séparer version moteur, cycle, commit ; pas de changement de protocole |
| R00-06 | index.html : 139 540 caractères ; live.js : 53 296 ; live-tools.js : 38 831 | modulariser en gardant design et navigation |
| R00-07 | preview_campus.PreviewHandler hérite serveur.Handler ; importe serveur (initialisation du répertoire DATA à l'import), mais ne lance ni init métier ni workers | préserver comportement aperçu, tester absence de mutation |
| R00-08 | tests patchent serveur.DB/config/request et moteur.fetch_page ; init appelle moteur.init avec module serveur | conserver les points de substitution, introduire un assemblage explicite par étapes |
| R00-09 | initialisation des tables répartie entre modules ; recovery et purge au démarrage | séparer schéma, migration et reprise dans un chantier ultérieur ; aucune migration de données R01/R02 |
| R00-10 | BILAN_V302.md et INSTALLATION_CAMPUS.md contiennent des statuts historiques | documenter la situation actuelle sans effacer les preuves historiques |

## R02 — critères de départ
R02.1 : inventaire reproductible basé sur git ls-files et analyse AST des imports Python ; distinguer imports directs/différés, rapport des cycles et des zones non analysées. Exclure données privées et archives. Aucun accès aux secrets, DB ou réseau.
R02.2 : spécification commune des chemins livrables, extensions et exclusions ; tester arborescence imbriquée, secrets, chemins invalides, liens, fichiers requis ; mêmes règles build et copie. Conserver les ressources historiques et valider le paquet sur une installation isolée.
R02.3 : métadonnées de livraison explicites (moteur et cycle distincts), vérifier les usages existants de BUILD_INFO et les artefacts CI avant de changer leurs noms. Ne pas changer VERSION à cette étape.
R02.4 : garde de non-régression packaging et test de migration existant ; aucun nouveau package métier avant ce feu vert.

## Continuité
R00 partiel, R01 documenté ; prochaine étape R02.1. Version stable main inchangée, travail en branche séparée, aucune fusion implicite. Pas de dépense API métier, pas de changement local. L'audit complet, les mesures de couverture et la validation opérationnelle locale restent à faire. Constitution et gouvernance feront l'objet d'un audit distinct avec leurs sources, sans réécrire les règles sur simple supposition.

## R02.1 — inventaire statique reproductible
Commande depuis V03 : `python audit_repository.py --summary` ; ajouter `--output chemin-nouveau.json` pour conserver le rapport. Analyse du commit Git (HEAD par défaut, ou --revision), pas de l'arbre de travail. Métadonnées des fichiers suivis et AST des blobs Python réguliers ; aucun import des modules de production. Exclusions de chemins privés par nom, pas un détecteur de secrets. Les imports hors graphe, chemins ambigus, imports dynamiques potentiels et échecs de parsing sont signalés. Les cycles distinguent portée module et imports différés, sans conclure à un bug. Analyse JS, couverture et code mort non établis.
CI : tests unitaires sur dépôt Git temporaire, inventaire du commit CI et artefact JSON. Aucun changement des modules métier ; résultat CI et inventaire réel à confirmer après exécution. R02.2 reste bloquée jusqu'à examen de ces résultats.

### Résultat R02.1
CI 45899136250 réussie (301 tests). Inventaire du commit de fusion CI a8398dcb : 195 chemins publics, 115 Python analysés, 46 modules runtime, 433 paires de dépendances tous types, zéro fichier Python ignoré ou ambigu, un groupe de cycles différés (autopilot, commercial, draft_recovery, periodic, planner, portfolio), zéro groupe de portée module. 566 imports externes/non résolus ; trois fichiers avec indices dynamiques. Un chemin privé exclu par nom, non inspecté. Rapport artefact 15155047575.
## R02.2 — politique de livraison commune
`release_paths.py` définit les chemins et extensions admis, les fichiers requis et le refus de collisions de casse/chemins invalides. Packages Python futurs : core, departments, tools, infrastructure, api, bootstrap ; docs et assets historiques à liste positive. Les deux textes racine INSTALLATION.txt et Lisez-moi.txt sont inclus ; config.example.json reste exclu comme auparavant. Build à partir des blobs du commit HEAD, pas des modifications locales. La copie de candidat local décompressé utilise la même politique et refuse liens et points de réanalyse dans l'espace parcouru ; elle n'atteste pas la provenance d'un répertoire local. Aucun changement des migrations ni des métadonnées historiques à ce stade. Tests : parité archive/copie, contenu privé exclu, modifications locales ignorées par build, liens, collisions, chemins invalides et fichiers requis. La liste positive n'est pas un détecteur de secrets et ne rend pas un candidat non fiable exécutable en sécurité. Validation CI requise avant R02.3.
