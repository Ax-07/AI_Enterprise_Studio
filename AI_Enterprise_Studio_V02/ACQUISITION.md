# V0.5.1 — préparation de l'acquisition (chantier)
 
## Ce qui est implémenté
- Migration SQLite additive, brouillon immuable par offre, empreinte de l'offre et langue.
- Aperçu HTML français hors ligne, échappé, sans scripts, formulaire ni action réseau. Les réserves sont reprises de l'offre interne. Ne pas publier ces brouillons internes.
- Parcours fictifs JSON, distincts des observations et des commandes. Ce ne sont pas des tests du produit ni des résultats de qualification réels.
- Routes locales protégées par la session propriétaire, révocation, export séparé; aucun appel IA ou n8n.
- Aucun changement du registre commercial ni démarrage d'une période d'observation.
 
## Contrat de la phase suivante (non implémenté)
Un canal public isolé, hébergé séparément et sans accès entrant au serveur propriétaire, doit disposer d'un stockage de demandes consenties, d'une durée de conservation bornée, d'un mécanisme de suppression, d'un quota et d'une expiration vérifiés côté canal. Un flux sortant local (n8n ou Python) récupère les événements authentifiés, rejette les rejeux et les références d'offre périmées, puis confirme leur réception après transaction locale. Les identifiants et contacts éventuels restent dans un stockage séparé et minimisé; le registre ne contient que les références pseudonymisées. La collecte et la publication ont des autorisations distinctes; la révocation doit arrêter la collecte sur le canal, même si le serveur local est hors ligne (expiration courte et renouvellement explicite de la capacité). Le mode test et le mode réel ne partagent pas de preuves ni de métriques.
 
Avant une activation réelle: choix du fournisseur et conditions de coût, identité du responsable de traitement et mentions légales, test de bout en bout, preuve de disponibilité du canal, validation du contenu public (ne pas exporter les notes internes) et autorisations du propriétaire. Ne pas démarrer les protocoles manuels existants pour simuler une acquisition.
 
Les brouillons français ne sont pas des traductions. Le parcours fictif ne teste pas le prototype. Le serveur conserve sa version stable pendant le chantier. Aucune mise à jour locale depuis cette branche avant validation et fusion.

## Canal isolé — nouveau banc de test
`public_channel.py` contient le moteur SQLite autonome; `public_channel_http.py` est un banc HTTP WSGI limité à 127.0.0.1, sans dépendance à l'application propriétaire. Il refuse les autorisations live, même signées. Deux mandats HMAC indépendants bornent publication et collecte à 24 h au maximum, quota maximum 1000 signaux de test. Le mandat de collecte dépend du contenu publié exact. Le navigateur doit confirmer son consentement et possède un jeton signé pseudonymisé; le quota ne se renouvelle pas après retrait. Les signaux peuvent être retirés à l'aide d'un code et sont purgés au premier traitement suivant 7 jours; une purge périodique indépendante du trafic reste nécessaire pour un service réel. Le dédoublonnage concerne un jeton par page, pas une personne réelle. Aucun nom, email, IP, secret de retrait brut ou commande payante dans les exports. Le mode TEST est affiché et les pages ne sont pas indexables.
 
Le banc n'est pas destiné à être exposé sur Internet. Il utilise HTTP local, un cookie sans attribut Secure pour ce contexte exclusivement, un serveur de développement et aucune infrastructure anti-abus distribuée. La clé HMAC de test est fournie via environnement (32 octets minimum), jamais via l'interface et jamais dans le dépôt. Le stockage doit être séparé. Les tests génèrent leurs propres clés factices. Ni déploiement, ni synchronisation avec l'entreprise, ni n8n, ni suivi de contact réel n'ont été effectués. Ne pas collecter de données personnelles ni utiliser ce banc avec des visiteurs réels. La qualification future devra distinguer les intentions autodéclarées des personnes vérifiées et les retraits devront être propagés au registre local.
