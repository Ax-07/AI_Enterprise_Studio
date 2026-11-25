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
