# Candidat D08.2 — installation parallèle (pas encore une version stable)

Ce paquet contient les sources publiques et le Design 22.6. Il n'embarque ni config.json local ni base de données. Le serveur conserve son numéro moteur 0.5.0 ; BUILD_INFO.json identifie le candidat par son commit. Python 3.11+ requis.

## Préparer sans démarrer

1. Arrêter toutes les missions et campagnes si possible, fermer le serveur historique avec Ctrl+C et attendre sa fermeture. Arrêter également le service TEST local. Ne pas utiliser les deux versions simultanément.
2. Extraire le ZIP dans un dossier temporaire distinct de l'installation actuelle.
3. Depuis le dossier extrait AI_Enterprise_Studio_V02, lancer (exemple Windows, chemins à adapter) :

```powershell
py -3 prepare_update.py --source "C:\\AI_Enterprise_Studio_V02" --destination "C:\\AI_Enterprise_Studio_Campus" --confirm-offline
```

Le script refuse un dossier cible existant. Il crée une sauvegarde SQLite cohérente, copie config.json localement s'il existe, initialise une **copie** avec les transports réseau interdits, vérifie l'intégrité et l'identité des écritures protégées. Les états actifs sont suspendus par les règles historiques de récupération. Les répertoires source et de sauvegarde restent disponibles. Le script ne lance aucun serveur.

PREPARATION.json contient uniquement des compteurs et indicateurs, pas de clé ou contenu de rapport. Les fichiers supplémentaires éventuels sous donnees/ ne sont pas copiés automatiquement (compteur dans le rapport) : conserver le dossier original, vérifier ces fichiers avant bascule. Les clés définies dans l'environnement système restent dans cet environnement. La sauvegarde locale contient potentiellement des secrets : ne jamais la publier ni la transmettre. Elle n'est pas un remplacement d'une sauvegarde externe sécurisée.

## Essais locaux (après validation du candidat)

Pour le premier contrôle, lancer LANCER_APERCU.bat dans le nouveau dossier (ou python preview_campus.py). Ouvrir http://127.0.0.1:8790/campus/live/. Ce serveur ne démarre aucun worker et refuse toutes les commandes ; l'interface historique est désactivée. Après validation locale, fermer cet aperçu et lancer LANCER_CAMPUS.bat (ou python serveur.py) pour passer en mode opérationnel. L'interface historique reste à la racine en mode opérationnel. Comparer l'historique, le registre des coûts et les livrables. Ne pas lancer une mission Cloud ni accorder une autorisation avant vérification. La reprise des activités payantes requiert une commande explicite. Les canaux TEST précédents ne sont pas réactivés automatiquement ; leur stockage distinct peut rester dans l'ancien emplacement.

## Retour à la version précédente

Avant toute nouvelle écriture métier dans le candidat : fermer le nouveau serveur et relancer l'ancien dossier, qui n'a pas été écrasé. Si des missions, dépenses, décisions ou transactions ont été enregistrées depuis la bascule, **ne pas repartir de l'ancienne base sans rapprochement** : cela effacerait les nouveaux engagements du point de vue du moteur. Garder les deux bases, arrêter les traitements et établir une procédure de rapprochement. Ne jamais écraser une base active ni réinitialiser un budget.

Le candidat n'est pas encore fusionné dans main. Les fonctionnalités historiques non encore migrées restent accessibles, notamment les modes spécialisés et certains formulaires commerciaux. Aucune vente ou diffusion réelle n'est activée par la mise à jour.
