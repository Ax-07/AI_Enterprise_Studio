# Correctif graphique V3.0.1 — aperçu local uniquement

À appliquer uniquement à AI_Enterprise_Studio_V03 V3.0.0 déjà préparée. Ce correctif contient 11 fichiers publics d'interface et de routage ; le moteur conserve VERSION 3.0.0. Aucun changement de schéma ni import de données. Ne remplace pas le dossier V03 avec le ZIP.

1. Ferme l'aperçu et tous les serveurs de l'application (y compris TEST local). Ne laisse aucune autre instance active. Le contrôle des ports 8790 et 8765 est une précaution supplémentaire, pas une détection exhaustive des processus.
2. Extrais le ZIP dans un nouveau dossier temporaire à côté de V03, jamais à l'intérieur.
3. Depuis le dossier extrait, dans PowerShell, lance :
   `py -3 apply_design_patch.py --target "..\AI_Enterprise_Studio_V03" --confirm-offline`
4. Si le rapport affiche installed:true, ouvre V03 et double-clique LANCER_DESIGN.bat. Le serveur d'aperçu ouvre /campus/original/ (lecture seule).
5. /campus/ reste la maquette ; /campus/live/ reste la vue précédente avec ses commandes uniquement en mode opérationnel ; LANCER_APERCU.bat reste inchangé.

La sauvegarde des seuls fichiers remplacés est créée à côté de V03 sous le nom AI_Enterprise_Studio_V03-sauvegarde-design-F06. Ne la supprime pas. Le script refuse toute version de départ inattendue ou sauvegarde existante. Il contrôle les empreintes du paquet et des fichiers installés, n'importe pas serveur.py, n'ouvre pas SQLite et ne copie ni config.json ni donnees ni PREPARATION.json. Les remplacements individuels sont atomiques, pas l'ensemble des fichiers ; après interruption, ne démarre aucun serveur avant restauration.

Retour en arrière : ferme tous les serveurs puis, depuis le même dossier de correctif, exécute :
`py -3 apply_design_patch.py --target "..\AI_Enterprise_Studio_V03" --confirm-offline --restore`
La sauvegarde est conservée ; les fichiers ajoutés par le correctif sont retirés, les autres restaurés après contrôle. Si un fichier a été modifié indépendamment, le script refuse de l'écraser. Aucun retour en arrière de la base de données. Pas de lancement opérationnel tant que le propriétaire n'a pas validé le rendu.

Ce paquet ne contient aucun fichier de données ni secret. Les empreintes servent à contrôler la cohérence du paquet ; télécharger uniquement depuis la CI de ce dépôt.
