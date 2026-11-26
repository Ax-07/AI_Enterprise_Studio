/* D03: static projection of Design 22.6 geometry and service labels. No engine state. Parity tested against D02. */
window.AESLiveLayout = [
  {
    "id": "ATLAS",
    "x": 122,
    "y": 122,
    "w": 100,
    "d": 91,
    "h": 105,
    "type": "hq",
    "color": "#49c9ff",
    "floors": [
      {
        "id": "LOBBY",
        "level": 0,
        "name": "Hall d’accueil",
        "description": "Accueil et orientation",
        "asset": "room_LOBBY.webp",
        "stations": [
          {
            "id": "LOBBY:station:0",
            "index": 0,
            "name": "Accueil numérique",
            "kind": "desk",
            "description": "Présentation et orientation",
            "destination": "welcome10"
          },
          {
            "id": "LOBBY:station:1",
            "index": 1,
            "name": "Annuaire",
            "kind": "wall",
            "description": "Les six agents",
            "destination": "classic"
          },
          {
            "id": "LOBBY:station:2",
            "index": 2,
            "name": "Espace visiteurs",
            "kind": "desk",
            "description": "Parcours des futurs clients",
            "destination": "visitors10"
          },
          {
            "id": "LOBBY:station:3",
            "index": 3,
            "name": "Missions",
            "kind": "screens",
            "description": "Campagnes en cours",
            "destination": "campaigns"
          },
          {
            "id": "LOBBY:station:4",
            "index": 4,
            "name": "Informations",
            "kind": "console",
            "description": "Présentation de l’entreprise",
            "destination": "about10"
          }
        ]
      },
      {
        "id": "ATLAS",
        "level": 1,
        "name": "Direction générale",
        "description": "Objectifs, missions et coordination",
        "asset": "room_ATLAS.webp",
        "stations": [
          {
            "id": "ATLAS:station:0",
            "index": 0,
            "name": "Table stratégique",
            "kind": "globe",
            "description": "Objectifs et arbitrages stratégiques",
            "destination": "agentDetail"
          },
          {
            "id": "ATLAS:station:1",
            "index": 1,
            "name": "Campagnes",
            "kind": "wall",
            "description": "Campagnes et livrables",
            "destination": "campaigns"
          },
          {
            "id": "ATLAS:station:2",
            "index": 2,
            "name": "Bureau d’ATLAS",
            "kind": "desk",
            "description": "Mission et responsabilité",
            "destination": "agentDetail"
          },
          {
            "id": "ATLAS:station:3",
            "index": 3,
            "name": "Supervision",
            "kind": "screens",
            "description": "Journal et activité des agents",
            "destination": "agentLog"
          },
          {
            "id": "ATLAS:station:4",
            "index": 4,
            "name": "Terminal propriétaire",
            "kind": "console",
            "description": "Validations et décisions réservées",
            "destination": "approval"
          }
        ]
      },
      {
        "id": "MEETING",
        "level": 2,
        "name": "Salle de réunion",
        "description": "Collaboration inter-agents",
        "asset": "room_MEETING.webp",
        "stations": [
          {
            "id": "MEETING:station:0",
            "index": 0,
            "name": "Table de réunion",
            "kind": "globe",
            "description": "Contributions des six agents",
            "destination": "meeting"
          },
          {
            "id": "MEETING:station:1",
            "index": 1,
            "name": "Ordre du jour",
            "kind": "wall",
            "description": "Objectifs et étapes de la campagne",
            "destination": "agenda"
          },
          {
            "id": "MEETING:station:2",
            "index": 2,
            "name": "Décisions",
            "kind": "desk",
            "description": "Arbitrages et points à vérifier",
            "destination": "decisions"
          },
          {
            "id": "MEETING:station:3",
            "index": 3,
            "name": "Missions",
            "kind": "screens",
            "description": "Centre des campagnes",
            "destination": "campaigns"
          },
          {
            "id": "MEETING:station:4",
            "index": 4,
            "name": "Compte rendu",
            "kind": "console",
            "description": "Télécharger le compte rendu fictif",
            "destination": "meetingExport"
          }
        ]
      },
      {
        "id": "SUPERVISION",
        "level": 3,
        "name": "Supervision autonome",
        "description": "Décisions et coordination",
        "asset": "room_SUPERVISION.webp",
        "stations": [
          {
            "id": "SUPERVISION:station:0",
            "index": 0,
            "name": "Table de supervision",
            "kind": "globe",
            "description": "Vue actuelle des échanges",
            "destination": "super13"
          },
          {
            "id": "SUPERVISION:station:1",
            "index": 1,
            "name": "Décisions ATLAS",
            "kind": "wall",
            "description": "Historique des délégations",
            "destination": "decisions13"
          },
          {
            "id": "SUPERVISION:station:2",
            "index": 2,
            "name": "Règles de contrôle",
            "kind": "desk",
            "description": "Garde-fous du moteur",
            "destination": "rules13"
          },
          {
            "id": "SUPERVISION:station:3",
            "index": 3,
            "name": "État du moteur",
            "kind": "screens",
            "description": "Import de données en lecture seule",
            "destination": "sync13"
          },
          {
            "id": "SUPERVISION:station:4",
            "index": 4,
            "name": "Rapport de supervision",
            "kind": "console",
            "description": "Exporter les traces",
            "destination": "superExport13"
          }
        ]
      },
      {
        "id": "NOTIFICATIONS",
        "level": 4,
        "name": "Centre de notifications",
        "description": "Priorités et événements",
        "asset": "room_NOTIFICATIONS.webp",
        "stations": [
          {
            "id": "NOTIFICATIONS:station:0",
            "index": 0,
            "name": "Radar des alertes",
            "kind": "shield",
            "description": "Notifications et filtres",
            "destination": "notifications"
          },
          {
            "id": "NOTIFICATIONS:station:1",
            "index": 1,
            "name": "À examiner",
            "kind": "wall",
            "description": "Alertes et validations",
            "destination": "unread"
          },
          {
            "id": "NOTIFICATIONS:station:2",
            "index": 2,
            "name": "Événements du moteur",
            "kind": "desk",
            "description": "États importés des agents",
            "destination": "agents"
          },
          {
            "id": "NOTIFICATIONS:station:3",
            "index": 3,
            "name": "Synchronisation",
            "kind": "screens",
            "description": "Importer un instantané",
            "destination": "sync"
          },
          {
            "id": "NOTIFICATIONS:station:4",
            "index": 4,
            "name": "Export des notifications",
            "kind": "console",
            "description": "Exporter les données affichées",
            "destination": "export"
          }
        ]
      },
      {
        "id": "PEOPLE17",
        "level": 5,
        "name": "Ressources & Compétences IA",
        "description": "Planification des équipes",
        "asset": null,
        "stations": [
          {
            "id": "PEOPLE17:station:0",
            "index": 0,
            "name": "Besoins",
            "kind": "globe",
            "description": "Examiner les besoins de compétences",
            "destination": "people17_0"
          },
          {
            "id": "PEOPLE17:station:1",
            "index": 1,
            "name": "Répartition",
            "kind": "screens",
            "description": "Consulter la répartition des spécialistes",
            "destination": "people17_1"
          },
          {
            "id": "PEOPLE17:station:2",
            "index": 2,
            "name": "Évaluation",
            "kind": "wall",
            "description": "Examiner les critères d’évaluation",
            "destination": "people17_2"
          },
          {
            "id": "PEOPLE17:station:3",
            "index": 3,
            "name": "Modèles IA",
            "kind": "console",
            "description": "Consulter les critères de choix des modèles",
            "destination": "people17_3"
          },
          {
            "id": "PEOPLE17:station:4",
            "index": 4,
            "name": "Mobilisation",
            "kind": "reactor",
            "description": "Ouvrir le centre de mobilisation",
            "destination": "mobil17"
          }
        ]
      },
      {
        "id": "GROUP",
        "level": 6,
        "name": "Centre des activités économiques",
        "description": "Filiales et diversification",
        "asset": "room_GROUP.webp",
        "stations": [
          {
            "id": "GROUP:station:0",
            "index": 0,
            "name": "Table du groupe",
            "kind": "globe",
            "description": "Vue consolidée",
            "destination": "group"
          },
          {
            "id": "GROUP:station:1",
            "index": 1,
            "name": "Quartiers spécialisés",
            "kind": "wall",
            "description": "Secteurs et départements",
            "destination": "districts"
          },
          {
            "id": "GROUP:station:2",
            "index": 2,
            "name": "Dossiers des activités",
            "kind": "desk",
            "description": "Filtrer les activités",
            "destination": "units"
          },
          {
            "id": "GROUP:station:3",
            "index": 3,
            "name": "Contrat de données",
            "kind": "screens",
            "description": "Importer un instantané",
            "destination": "sync"
          },
          {
            "id": "GROUP:station:4",
            "index": 4,
            "name": "Rapport du groupe",
            "kind": "console",
            "description": "Exporter les données affichées",
            "destination": "export"
          }
        ]
      },
      {
        "id": "EXPAND",
        "level": 7,
        "name": "Planification & croissance verticale",
        "description": "Capacité des bâtiments et besoins durables",
        "asset": "room_EXPAND.webp",
        "stations": [
          {
            "id": "EXPAND:station:0",
            "index": 0,
            "name": "Plan des étages",
            "kind": "arm",
            "description": "Consulter les capacités verticales",
            "destination": "expansion10"
          },
          {
            "id": "EXPAND:station:1",
            "index": 1,
            "name": "Capacité",
            "kind": "wall",
            "description": "Besoins et infrastructures",
            "destination": "capacity10"
          },
          {
            "id": "EXPAND:station:2",
            "index": 2,
            "name": "Budget de croissance",
            "kind": "desk",
            "description": "Conditions financières",
            "destination": "growthBudget10"
          },
          {
            "id": "EXPAND:station:3",
            "index": 3,
            "name": "Jalons",
            "kind": "screens",
            "description": "Critères de passage",
            "destination": "milestones10"
          },
          {
            "id": "EXPAND:station:4",
            "index": 4,
            "name": "Plan vertical",
            "kind": "console",
            "description": "Exporter la répartition des étages",
            "destination": "growthExport10"
          }
        ]
      },
      {
        "id": "OWNER",
        "level": 8,
        "name": "Bureau du propriétaire",
        "description": "Supervision et décisions réservées",
        "asset": "room_OWNER.webp",
        "stations": [
          {
            "id": "OWNER:station:0",
            "index": 0,
            "name": "Table stratégique",
            "kind": "globe",
            "description": "Objectifs et stratégie globale",
            "destination": "strategy"
          },
          {
            "id": "OWNER:station:1",
            "index": 1,
            "name": "Supervision",
            "kind": "wall",
            "description": "Vue classique de tous les agents",
            "destination": "classic"
          },
          {
            "id": "OWNER:station:2",
            "index": 2,
            "name": "Bureau exécutif",
            "kind": "desk",
            "description": "Campagnes et dossiers de l’entreprise",
            "destination": "campaigns"
          },
          {
            "id": "OWNER:station:3",
            "index": 3,
            "name": "Situation financière",
            "kind": "screens",
            "description": "Revenus, dépenses et budgets",
            "destination": "finance"
          },
          {
            "id": "OWNER:station:4",
            "index": 4,
            "name": "Validations",
            "kind": "console",
            "description": "Décisions et autorisations réservées",
            "destination": "approval"
          }
        ]
      }
    ]
  },
  {
    "id": "ORION",
    "x": 62,
    "y": 253,
    "w": 95,
    "d": 74,
    "h": 48,
    "type": "lab",
    "color": "#48f4ad",
    "floors": [
      {
        "id": "ORION",
        "level": 0,
        "name": "Laboratoire de recherche",
        "description": "Études, veille et spécialistes",
        "asset": "room_ORION.webp",
        "stations": [
          {
            "id": "ORION:station:0",
            "index": 0,
            "name": "Globe des marchés",
            "kind": "globe",
            "description": "Analyse des marchés internationaux",
            "destination": "markets"
          },
          {
            "id": "ORION:station:1",
            "index": 1,
            "name": "Opportunités",
            "kind": "wall",
            "description": "Classement économique des pistes",
            "destination": "opportunities"
          },
          {
            "id": "ORION:station:2",
            "index": 2,
            "name": "Station de recherche",
            "kind": "desk",
            "description": "Mission de recherche et sources",
            "destination": "agentDetail"
          },
          {
            "id": "ORION:station:3",
            "index": 3,
            "name": "Sources vérifiées",
            "kind": "screens",
            "description": "Données publiques et connecteurs",
            "destination": "connectors"
          },
          {
            "id": "ORION:station:4",
            "index": 4,
            "name": "Archives d’études",
            "kind": "rack",
            "description": "Synthèses et connaissances",
            "destination": "memory"
          }
        ]
      },
      {
        "id": "WORLD",
        "level": 1,
        "name": "Observatoire international",
        "description": "Exploration des marchés",
        "asset": "room_WORLD.webp",
        "stations": [
          {
            "id": "WORLD:station:0",
            "index": 0,
            "name": "Carte mondiale",
            "kind": "globe",
            "description": "Carte interactive des marchés",
            "destination": "world"
          },
          {
            "id": "WORLD:station:1",
            "index": 1,
            "name": "Europe",
            "kind": "wall",
            "description": "Zone de recherche illustrative",
            "destination": "region:EU"
          },
          {
            "id": "WORLD:station:2",
            "index": 2,
            "name": "Amérique du Nord",
            "kind": "desk",
            "description": "Zone de recherche illustrative",
            "destination": "region:NA"
          },
          {
            "id": "WORLD:station:3",
            "index": 3,
            "name": "Asie-Pacifique",
            "kind": "screens",
            "description": "Zone de recherche illustrative",
            "destination": "region:AP"
          },
          {
            "id": "WORLD:station:4",
            "index": 4,
            "name": "Sources et études",
            "kind": "console",
            "description": "Connaissances et sources",
            "destination": "memory"
          }
        ]
      },
      {
        "id": "OPPORTUNITIES",
        "level": 2,
        "name": "Centre des opportunités",
        "description": "Recherche et priorisation",
        "asset": "room_OPPORTUNITIES.webp",
        "stations": [
          {
            "id": "OPPORTUNITIES:station:0",
            "index": 0,
            "name": "Radar des marchés",
            "kind": "dish",
            "description": "Opportunités classées",
            "destination": "opportunities"
          },
          {
            "id": "OPPORTUNITIES:station:1",
            "index": 1,
            "name": "Sources et preuves",
            "kind": "wall",
            "description": "Vérification documentaire",
            "destination": "evidence"
          },
          {
            "id": "OPPORTUNITIES:station:2",
            "index": 2,
            "name": "Marchés par secteur",
            "kind": "desk",
            "description": "Répartition par activité",
            "destination": "districts"
          },
          {
            "id": "OPPORTUNITIES:station:3",
            "index": 3,
            "name": "Priorités de recherche",
            "kind": "screens",
            "description": "Filtrer les opportunités",
            "destination": "opportunities"
          },
          {
            "id": "OPPORTUNITIES:station:4",
            "index": 4,
            "name": "Dossier des opportunités",
            "kind": "console",
            "description": "Exporter le portefeuille V2 complet",
            "destination": "export"
          }
        ]
      }
    ]
  },
  {
    "id": "NEXUS",
    "x": 60,
    "y": 402,
    "w": 87,
    "d": 75,
    "h": 51,
    "type": "factory",
    "color": "#37dded",
    "floors": [
      {
        "id": "NEXUS",
        "level": 0,
        "name": "Bureaux de production",
        "description": "Développement et spécialistes",
        "asset": "room_NEXUS.webp",
        "stations": [
          {
            "id": "NEXUS:station:0",
            "index": 0,
            "name": "Prototypage",
            "kind": "arm",
            "description": "Prototype de rapprochement",
            "destination": "campaignDetail"
          },
          {
            "id": "NEXUS:station:1",
            "index": 1,
            "name": "Produits",
            "kind": "wall",
            "description": "Projets en développement",
            "destination": "campaigns"
          },
          {
            "id": "NEXUS:station:2",
            "index": 2,
            "name": "Programmation",
            "kind": "desk",
            "description": "Mission de production",
            "destination": "agentDetail"
          },
          {
            "id": "NEXUS:station:3",
            "index": 3,
            "name": "Livrables",
            "kind": "rack",
            "description": "Télécharger le dossier fictif",
            "destination": "export"
          },
          {
            "id": "NEXUS:station:4",
            "index": 4,
            "name": "Automatisation",
            "kind": "console",
            "description": "Catalogue n8n et connecteurs",
            "destination": "connectors"
          }
        ]
      },
      {
        "id": "FACTORY",
        "level": 1,
        "name": "Chaîne de production",
        "description": "Cycle de vie des produits",
        "asset": "room_FACTORY.webp",
        "stations": [
          {
            "id": "FACTORY:station:0",
            "index": 0,
            "name": "Chaîne d’assemblage",
            "kind": "arm",
            "description": "Suivi des six étapes du produit",
            "destination": "pipeline"
          },
          {
            "id": "FACTORY:station:1",
            "index": 1,
            "name": "Cahier des charges",
            "kind": "wall",
            "description": "Besoin et conception",
            "destination": "spec"
          },
          {
            "id": "FACTORY:station:2",
            "index": 2,
            "name": "Prototype",
            "kind": "desk",
            "description": "État du prototype",
            "destination": "prototype"
          },
          {
            "id": "FACTORY:station:3",
            "index": 3,
            "name": "Contrôles qualité",
            "kind": "screens",
            "description": "Critères de validation",
            "destination": "quality"
          },
          {
            "id": "FACTORY:station:4",
            "index": 4,
            "name": "Livrables",
            "kind": "console",
            "description": "Exporter le dossier fictif",
            "destination": "export"
          }
        ]
      },
      {
        "id": "LAB",
        "level": 2,
        "name": "Laboratoire d’innovation",
        "description": "Recherche et développement",
        "asset": "room_LAB.webp",
        "stations": [
          {
            "id": "LAB:station:0",
            "index": 0,
            "name": "Incubateur",
            "kind": "reactor",
            "description": "Portefeuille expérimental",
            "destination": "ideas10"
          },
          {
            "id": "LAB:station:1",
            "index": 1,
            "name": "Hypothèses",
            "kind": "wall",
            "description": "Questions à vérifier",
            "destination": "hypotheses10"
          },
          {
            "id": "LAB:station:2",
            "index": 2,
            "name": "Prototypes",
            "kind": "desk",
            "description": "Expérimentations et livrables",
            "destination": "experiments10"
          },
          {
            "id": "LAB:station:3",
            "index": 3,
            "name": "Évaluation",
            "kind": "screens",
            "description": "Critères de décision",
            "destination": "review10"
          },
          {
            "id": "LAB:station:4",
            "index": 4,
            "name": "Dossier R&D",
            "kind": "console",
            "description": "Exporter le dossier fictif",
            "destination": "innovationExport10"
          }
        ]
      },
      {
        "id": "PORTFOLIO",
        "level": 3,
        "name": "Portefeuille de produits",
        "description": "Cycle de développement",
        "asset": "room_PORTFOLIO.webp",
        "stations": [
          {
            "id": "PORTFOLIO:station:0",
            "index": 0,
            "name": "Vitrine du portefeuille",
            "kind": "reactor",
            "description": "Produits et services",
            "destination": "products"
          },
          {
            "id": "PORTFOLIO:station:1",
            "index": 1,
            "name": "Pipeline produit",
            "kind": "wall",
            "description": "Cycle de développement",
            "destination": "pipeline"
          },
          {
            "id": "PORTFOLIO:station:2",
            "index": 2,
            "name": "Atelier de suivi",
            "kind": "desk",
            "description": "Dossiers par activité",
            "destination": "products"
          },
          {
            "id": "PORTFOLIO:station:3",
            "index": 3,
            "name": "Contrôles de publication",
            "kind": "screens",
            "description": "Règles de commercialisation",
            "destination": "controls"
          },
          {
            "id": "PORTFOLIO:station:4",
            "index": 4,
            "name": "Export du portefeuille",
            "kind": "console",
            "description": "Exporter les données affichées",
            "destination": "export"
          }
        ]
      },
      {
        "id": "FULFILL17",
        "level": 4,
        "name": "Livraison & Exploitation",
        "description": "Commandes et services",
        "asset": null,
        "stations": [
          {
            "id": "FULFILL17:station:0",
            "index": 0,
            "name": "Commandes",
            "kind": "screens",
            "description": "Consulter les commandes",
            "destination": "fulfill17_0"
          },
          {
            "id": "FULFILL17:station:1",
            "index": 1,
            "name": "Livraison",
            "kind": "arm",
            "description": "Examiner les livraisons",
            "destination": "fulfill17_1"
          },
          {
            "id": "FULFILL17:station:2",
            "index": 2,
            "name": "Activations",
            "kind": "reactor",
            "description": "Consulter les activations de services",
            "destination": "fulfill17_2"
          },
          {
            "id": "FULFILL17:station:3",
            "index": 3,
            "name": "Suivi service",
            "kind": "wall",
            "description": "Consulter le suivi des services livrés",
            "destination": "fulfill17_3"
          },
          {
            "id": "FULFILL17:station:4",
            "index": 4,
            "name": "Conformité",
            "kind": "console",
            "description": "Examiner les contrôles avant remise",
            "destination": "fulfill17_4"
          }
        ]
      }
    ]
  },
  {
    "id": "MIDAS",
    "x": 402,
    "y": 60,
    "w": 82,
    "d": 76,
    "h": 67,
    "type": "finance",
    "color": "#ffcc67",
    "floors": [
      {
        "id": "MIDAS",
        "level": 0,
        "name": "Direction financière",
        "description": "Budgets, trésorerie et spécialistes",
        "asset": "room_MIDAS.webp",
        "stations": [
          {
            "id": "MIDAS:station:0",
            "index": 0,
            "name": "Coffre numérique",
            "kind": "vault",
            "description": "Trésorerie et revenus fictifs",
            "destination": "finance"
          },
          {
            "id": "MIDAS:station:1",
            "index": 1,
            "name": "Mur financier",
            "kind": "wall",
            "description": "Résultat et marges",
            "destination": "finance"
          },
          {
            "id": "MIDAS:station:2",
            "index": 2,
            "name": "Bureau de MIDAS",
            "kind": "desk",
            "description": "Mission financière",
            "destination": "agentDetail"
          },
          {
            "id": "MIDAS:station:3",
            "index": 3,
            "name": "Coûts API",
            "kind": "screens",
            "description": "Budget et dépenses simulés",
            "destination": "finance"
          },
          {
            "id": "MIDAS:station:4",
            "index": 4,
            "name": "Investissements",
            "kind": "console",
            "description": "Hypothèses de rentabilité",
            "destination": "profit"
          }
        ]
      },
      {
        "id": "ECON",
        "level": 1,
        "name": "Centre économique",
        "description": "Performance et allocation du capital",
        "asset": "room_ECON.webp",
        "stations": [
          {
            "id": "ECON:station:0",
            "index": 0,
            "name": "Performance",
            "kind": "globe",
            "description": "Graphique de démonstration",
            "destination": "performance10"
          },
          {
            "id": "ECON:station:1",
            "index": 1,
            "name": "Revenus et dépenses",
            "kind": "wall",
            "description": "Tableau de bord financier",
            "destination": "finance"
          },
          {
            "id": "ECON:station:2",
            "index": 2,
            "name": "Investissements",
            "kind": "desk",
            "description": "Évaluation des projets",
            "destination": "invest10"
          },
          {
            "id": "ECON:station:3",
            "index": 3,
            "name": "Prévisions",
            "kind": "screens",
            "description": "Scénarios économiques",
            "destination": "forecast10"
          },
          {
            "id": "ECON:station:4",
            "index": 4,
            "name": "Rapport financier",
            "kind": "console",
            "description": "Exporter un scénario fictif",
            "destination": "economyExport10"
          }
        ]
      },
      {
        "id": "INVESTMENTS",
        "level": 2,
        "name": "Salle des investissements",
        "description": "Arbitrage des ressources",
        "asset": "room_INVESTMENTS.webp",
        "stations": [
          {
            "id": "INVESTMENTS:station:0",
            "index": 0,
            "name": "Table d’allocation",
            "kind": "vault",
            "description": "Investissements envisagés",
            "destination": "investments"
          },
          {
            "id": "INVESTMENTS:station:1",
            "index": 1,
            "name": "Répartition des budgets",
            "kind": "wall",
            "description": "Enveloppes par secteur",
            "destination": "allocation"
          },
          {
            "id": "INVESTMENTS:station:2",
            "index": 2,
            "name": "Dossiers d’investissement",
            "kind": "desk",
            "description": "Hypothèses et états",
            "destination": "investments"
          },
          {
            "id": "INVESTMENTS:station:3",
            "index": 3,
            "name": "Contrôles budgétaires",
            "kind": "screens",
            "description": "Règles avant décision",
            "destination": "controls"
          },
          {
            "id": "INVESTMENTS:station:4",
            "index": 4,
            "name": "Rapport d’allocation",
            "kind": "console",
            "description": "Exporter les données affichées",
            "destination": "export"
          }
        ]
      },
      {
        "id": "BUY17",
        "level": 3,
        "name": "Achats & Fournisseurs",
        "description": "Prestataires et engagements",
        "asset": null,
        "stations": [
          {
            "id": "BUY17:station:0",
            "index": 0,
            "name": "Fournisseurs",
            "kind": "screens",
            "description": "Consulter le registre des fournisseurs",
            "destination": "buy17_0"
          },
          {
            "id": "BUY17:station:1",
            "index": 1,
            "name": "Abonnements",
            "kind": "wall",
            "description": "Examiner les abonnements",
            "destination": "buy17_1"
          },
          {
            "id": "BUY17:station:2",
            "index": 2,
            "name": "Comparatifs",
            "kind": "globe",
            "description": "Comparer les offres",
            "destination": "buy17_2"
          },
          {
            "id": "BUY17:station:3",
            "index": 3,
            "name": "Demandes achat",
            "kind": "vault",
            "description": "Examiner les demandes d’achat",
            "destination": "buy17_3"
          },
          {
            "id": "BUY17:station:4",
            "index": 4,
            "name": "Budget",
            "kind": "console",
            "description": "Consulter le module financier",
            "destination": "finance"
          }
        ]
      }
    ]
  },
  {
    "id": "HERMES",
    "x": 260,
    "y": 62,
    "w": 86,
    "d": 82,
    "h": 62,
    "type": "comms",
    "color": "#c783ff",
    "floors": [
      {
        "id": "HERMES",
        "level": 0,
        "name": "Commerce & Marketing",
        "description": "Ventes, marketing et spécialistes",
        "asset": "room_HERMES.webp",
        "stations": [
          {
            "id": "HERMES:station:0",
            "index": 0,
            "name": "Communication",
            "kind": "dish",
            "description": "Stratégie et communication",
            "destination": "agentDetail"
          },
          {
            "id": "HERMES:station:1",
            "index": 1,
            "name": "Campagnes marketing",
            "kind": "wall",
            "description": "Suivi des campagnes",
            "destination": "campaigns"
          },
          {
            "id": "HERMES:station:2",
            "index": 2,
            "name": "Station commerciale",
            "kind": "desk",
            "description": "Parcours client",
            "destination": "agentDetail"
          },
          {
            "id": "HERMES:station:3",
            "index": 3,
            "name": "Prospects",
            "kind": "screens",
            "description": "Pipeline de démonstration",
            "destination": "leads"
          },
          {
            "id": "HERMES:station:4",
            "index": 4,
            "name": "Ventes",
            "kind": "console",
            "description": "Revenus et commercialisation",
            "destination": "finance"
          }
        ]
      },
      {
        "id": "SHOWROOM",
        "level": 1,
        "name": "Showroom commercial",
        "description": "Catalogue et démonstrations",
        "asset": "room_SHOWROOM.webp",
        "stations": [
          {
            "id": "SHOWROOM:station:0",
            "index": 0,
            "name": "Vitrine numérique",
            "kind": "reactor",
            "description": "Catalogue filtrable",
            "destination": "catalog12"
          },
          {
            "id": "SHOWROOM:station:1",
            "index": 1,
            "name": "Produits numériques",
            "kind": "wall",
            "description": "Concepts produits",
            "destination": "products12"
          },
          {
            "id": "SHOWROOM:station:2",
            "index": 2,
            "name": "Services",
            "kind": "desk",
            "description": "Concepts de services",
            "destination": "services12"
          },
          {
            "id": "SHOWROOM:station:3",
            "index": 3,
            "name": "Contrôle avant vente",
            "kind": "screens",
            "description": "Étapes de mise en marché",
            "destination": "readiness12"
          },
          {
            "id": "SHOWROOM:station:4",
            "index": 4,
            "name": "Catalogue export",
            "kind": "console",
            "description": "Télécharger les concepts",
            "destination": "catalogExport12"
          }
        ]
      },
      {
        "id": "SUPPORT17",
        "level": 2,
        "name": "Service client",
        "description": "Assistance et après-vente",
        "asset": null,
        "stations": [
          {
            "id": "SUPPORT17:station:0",
            "index": 0,
            "name": "Demandes",
            "kind": "screens",
            "description": "Consulter les demandes clients",
            "destination": "support17_0"
          },
          {
            "id": "SUPPORT17:station:1",
            "index": 1,
            "name": "Réclamations",
            "kind": "wall",
            "description": "Examiner les réclamations",
            "destination": "support17_1"
          },
          {
            "id": "SUPPORT17:station:2",
            "index": 2,
            "name": "Remboursements",
            "kind": "vault",
            "description": "Examiner les demandes de remboursement",
            "destination": "support17_2"
          },
          {
            "id": "SUPPORT17:station:3",
            "index": 3,
            "name": "Satisfaction",
            "kind": "globe",
            "description": "Consulter les retours clients",
            "destination": "support17_3"
          },
          {
            "id": "SUPPORT17:station:4",
            "index": 4,
            "name": "Aide & FAQ",
            "kind": "console",
            "description": "Consulter la documentation client",
            "destination": "support17_4"
          }
        ]
      },
      {
        "id": "COMMS",
        "level": 3,
        "name": "Centre de communication",
        "description": "Échanges et traçabilité",
        "asset": "room_COMMS.webp",
        "stations": [
          {
            "id": "COMMS:station:0",
            "index": 0,
            "name": "Réseau holographique",
            "kind": "dish",
            "description": "Voir le flux actuel",
            "destination": "network12"
          },
          {
            "id": "COMMS:station:1",
            "index": 1,
            "name": "Journal interne",
            "kind": "wall",
            "description": "Filtrer les transmissions",
            "destination": "messages12"
          },
          {
            "id": "COMMS:station:2",
            "index": 2,
            "name": "Canaux externes",
            "kind": "desk",
            "description": "Catalogue des connecteurs",
            "destination": "connectors"
          },
          {
            "id": "COMMS:station:3",
            "index": 3,
            "name": "Règles de diffusion",
            "kind": "screens",
            "description": "Autorisations et sécurité",
            "destination": "policy12"
          },
          {
            "id": "COMMS:station:4",
            "index": 4,
            "name": "Archive des échanges",
            "kind": "console",
            "description": "Exporter le journal",
            "destination": "commsExport12"
          }
        ]
      },
      {
        "id": "ADS183",
        "level": 4,
        "name": "Studio publicitaire",
        "description": "Création et campagnes publicitaires",
        "asset": null,
        "stations": [
          {
            "id": "ADS183:station:0",
            "index": 0,
            "name": "Brief",
            "kind": "desk",
            "description": "Définir le brief publicitaire",
            "destination": "ads183_0"
          },
          {
            "id": "ADS183:station:1",
            "index": 1,
            "name": "Créations",
            "kind": "wall",
            "description": "Examiner les textes et visuels",
            "destination": "ads183_1"
          },
          {
            "id": "ADS183:station:2",
            "index": 2,
            "name": "Audiences",
            "kind": "globe",
            "description": "Examiner les audiences et canaux",
            "destination": "ads183_2"
          },
          {
            "id": "ADS183:station:3",
            "index": 3,
            "name": "Plan média",
            "kind": "screens",
            "description": "Examiner le plan média",
            "destination": "ads183_3"
          },
          {
            "id": "ADS183:station:4",
            "index": 4,
            "name": "Contrôles",
            "kind": "shield",
            "description": "Examiner les contrôles avant campagne",
            "destination": "ads183_4"
          }
        ]
      },
      {
        "id": "VIDEO183",
        "level": 5,
        "name": "Studio audiovisuel",
        "description": "Production vidéo, audio et montage",
        "asset": null,
        "stations": [
          {
            "id": "VIDEO183:station:0",
            "index": 0,
            "name": "Scénario",
            "kind": "desk",
            "description": "Consulter le scénario vidéo",
            "destination": "video183_0"
          },
          {
            "id": "VIDEO183:station:1",
            "index": 1,
            "name": "Génération",
            "kind": "camera183",
            "description": "Examiner les demandes de génération",
            "destination": "video183_1"
          },
          {
            "id": "VIDEO183:station:2",
            "index": 2,
            "name": "Voix & son",
            "kind": "console",
            "description": "Examiner les ressources audio",
            "destination": "video183_2"
          },
          {
            "id": "VIDEO183:station:3",
            "index": 3,
            "name": "Montage",
            "kind": "screens",
            "description": "Examiner le montage et les variantes",
            "destination": "video183_3"
          },
          {
            "id": "VIDEO183:station:4",
            "index": 4,
            "name": "Qualité",
            "kind": "shield",
            "description": "Examiner la vérification audiovisuelle",
            "destination": "video183_4"
          }
        ]
      },
      {
        "id": "PUBLISH183",
        "level": 6,
        "name": "Centre de diffusion",
        "description": "YouTube et réseaux sociaux",
        "asset": null,
        "stations": [
          {
            "id": "PUBLISH183:station:0",
            "index": 0,
            "name": "YouTube",
            "kind": "screens",
            "description": "Consulter le dossier de chaîne YouTube",
            "destination": "publish183_0"
          },
          {
            "id": "PUBLISH183:station:1",
            "index": 1,
            "name": "Réseaux",
            "kind": "dish",
            "description": "Examiner les canaux sociaux",
            "destination": "publish183_1"
          },
          {
            "id": "PUBLISH183:station:2",
            "index": 2,
            "name": "Calendrier",
            "kind": "wall",
            "description": "Consulter le calendrier éditorial",
            "destination": "publish183_2"
          },
          {
            "id": "PUBLISH183:station:3",
            "index": 3,
            "name": "Publication",
            "kind": "console",
            "description": "Examiner la file de publication",
            "destination": "publish183_3"
          },
          {
            "id": "PUBLISH183:station:4",
            "index": 4,
            "name": "Journal",
            "kind": "rack",
            "description": "Consulter le journal de diffusion",
            "destination": "publish183_4"
          }
        ]
      },
      {
        "id": "ANALYTICS183",
        "level": 7,
        "name": "Analyse marketing",
        "description": "Audience, conversions et rentabilité",
        "asset": null,
        "stations": [
          {
            "id": "ANALYTICS183:station:0",
            "index": 0,
            "name": "Audience",
            "kind": "globe",
            "description": "Consulter les indicateurs d’audience",
            "destination": "analytics183_0"
          },
          {
            "id": "ANALYTICS183:station:1",
            "index": 1,
            "name": "Conversions",
            "kind": "screens",
            "description": "Examiner les conversions",
            "destination": "analytics183_1"
          },
          {
            "id": "ANALYTICS183:station:2",
            "index": 2,
            "name": "Rentabilité",
            "kind": "vault",
            "description": "Examiner la rentabilité publicitaire",
            "destination": "analytics183_2"
          },
          {
            "id": "ANALYTICS183:station:3",
            "index": 3,
            "name": "Attribution",
            "kind": "wall",
            "description": "Examiner la fiabilité des mesures",
            "destination": "analytics183_3"
          },
          {
            "id": "ANALYTICS183:station:4",
            "index": 4,
            "name": "Optimisation",
            "kind": "console",
            "description": "Examiner les recommandations",
            "destination": "analytics183_4"
          }
        ]
      }
    ]
  },
  {
    "id": "SENTINEL",
    "x": 249,
    "y": 402,
    "w": 88,
    "d": 76,
    "h": 49,
    "type": "security",
    "color": "#ff9c67",
    "floors": [
      {
        "id": "SENTINEL",
        "level": 0,
        "name": "Contrôle & Sécurité",
        "description": "Contrôles, risques et spécialistes",
        "asset": "room_SENTINEL.webp",
        "stations": [
          {
            "id": "SENTINEL:station:0",
            "index": 0,
            "name": "Bouclier de contrôle",
            "kind": "shield",
            "description": "Risques et autorisations",
            "destination": "approval"
          },
          {
            "id": "SENTINEL:station:1",
            "index": 1,
            "name": "Mur de surveillance",
            "kind": "wall",
            "description": "Journal de contrôle",
            "destination": "agentLog"
          },
          {
            "id": "SENTINEL:station:2",
            "index": 2,
            "name": "Bureau de SENTINEL",
            "kind": "desk",
            "description": "Mission de vérification",
            "destination": "agentDetail"
          },
          {
            "id": "SENTINEL:station:3",
            "index": 3,
            "name": "Contrôle qualité",
            "kind": "screens",
            "description": "Livrables et vérifications",
            "destination": "campaigns"
          },
          {
            "id": "SENTINEL:station:4",
            "index": 4,
            "name": "Diagnostics",
            "kind": "console",
            "description": "Connecteurs et incidents",
            "destination": "connectors"
          }
        ]
      },
      {
        "id": "INCIDENTS",
        "level": 1,
        "name": "Centre des incidents",
        "description": "Diagnostic et résolution",
        "asset": "room_INCIDENTS.webp",
        "stations": [
          {
            "id": "INCIDENTS:station:0",
            "index": 0,
            "name": "Radar des incidents",
            "kind": "globe",
            "description": "Tableau des incidents",
            "destination": "incidents13"
          },
          {
            "id": "INCIDENTS:station:1",
            "index": 1,
            "name": "Diagnostic",
            "kind": "wall",
            "description": "Examiner les causes",
            "destination": "incidents13"
          },
          {
            "id": "INCIDENTS:station:2",
            "index": 2,
            "name": "Plan de résolution",
            "kind": "desk",
            "description": "Étapes de traitement",
            "destination": "incidents13"
          },
          {
            "id": "INCIDENTS:station:3",
            "index": 3,
            "name": "Garde-fous",
            "kind": "screens",
            "description": "Règles de sécurité",
            "destination": "rules13"
          },
          {
            "id": "INCIDENTS:station:4",
            "index": 4,
            "name": "Rapport d’incidents",
            "kind": "console",
            "description": "Exporter les exercices",
            "destination": "incidentExport13"
          }
        ]
      },
      {
        "id": "LEGAL17",
        "level": 2,
        "name": "Administration & Juridique",
        "description": "Obligations et documents",
        "asset": null,
        "stations": [
          {
            "id": "LEGAL17:station:0",
            "index": 0,
            "name": "Contrats",
            "kind": "screens",
            "description": "Examiner les dossiers contractuels",
            "destination": "legal17_0"
          },
          {
            "id": "LEGAL17:station:1",
            "index": 1,
            "name": "Licences",
            "kind": "wall",
            "description": "Contrôler les licences et droits",
            "destination": "legal17_1"
          },
          {
            "id": "LEGAL17:station:2",
            "index": 2,
            "name": "Confidentialité",
            "kind": "shield",
            "description": "Examiner les traitements de données",
            "destination": "legal17_2"
          },
          {
            "id": "LEGAL17:station:3",
            "index": 3,
            "name": "Obligations",
            "kind": "console",
            "description": "Consulter le registre des obligations",
            "destination": "legal17_3"
          },
          {
            "id": "LEGAL17:station:4",
            "index": 4,
            "name": "Validations",
            "kind": "vault",
            "description": "Consulter les validations réservées",
            "destination": "legal17_4"
          }
        ]
      }
    ]
  },
  {
    "id": "CORE",
    "x": 402,
    "y": 249,
    "w": 84,
    "d": 84,
    "h": 45,
    "type": "core",
    "color": "#78a9ff",
    "floors": [
      {
        "id": "INFRA",
        "level": 0,
        "name": "Infrastructure technique",
        "description": "Connecteurs et automatisations",
        "asset": "room_INFRA.webp",
        "stations": [
          {
            "id": "INFRA:station:0",
            "index": 0,
            "name": "Nœud central",
            "kind": "rack",
            "description": "Schéma des échanges",
            "destination": "network"
          },
          {
            "id": "INFRA:station:1",
            "index": 1,
            "name": "Connecteurs",
            "kind": "rack",
            "description": "Catalogue des connecteurs",
            "destination": "connectors"
          },
          {
            "id": "INFRA:station:2",
            "index": 2,
            "name": "Workflows n8n",
            "kind": "rack",
            "description": "Exemple de pipeline autorisé",
            "destination": "workflow"
          },
          {
            "id": "INFRA:station:3",
            "index": 3,
            "name": "Journal technique",
            "kind": "rack",
            "description": "Événements et diagnostics fictifs",
            "destination": "logs"
          },
          {
            "id": "INFRA:station:4",
            "index": 4,
            "name": "Budget et sécurité",
            "kind": "console",
            "description": "Limites et contrôles",
            "destination": "limits"
          }
        ]
      },
      {
        "id": "CORE",
        "level": 1,
        "name": "Mémoire collective",
        "description": "Connaissances et équipes modulaires",
        "asset": "room_CORE.webp",
        "stations": [
          {
            "id": "CORE:station:0",
            "index": 0,
            "name": "Réacteur de données",
            "kind": "reactor",
            "description": "Connaissances de l’entreprise",
            "destination": "memory"
          },
          {
            "id": "CORE:station:1",
            "index": 1,
            "name": "Bibliothèque",
            "kind": "rack",
            "description": "Documents et connaissances",
            "destination": "memory"
          },
          {
            "id": "CORE:station:2",
            "index": 2,
            "name": "Terminal d’apprentissage",
            "kind": "desk",
            "description": "Mission d’indexation",
            "destination": "agentDetail"
          },
          {
            "id": "CORE:station:3",
            "index": 3,
            "name": "Serveurs",
            "kind": "rack",
            "description": "Historique et index",
            "destination": "agentLog"
          },
          {
            "id": "CORE:station:4",
            "index": 4,
            "name": "Archives",
            "kind": "console",
            "description": "Dossiers de campagnes",
            "destination": "campaigns"
          }
        ]
      },
      {
        "id": "ITOPS17",
        "level": 2,
        "name": "Exploitation informatique",
        "description": "Disponibilité et maintenance",
        "asset": null,
        "stations": [
          {
            "id": "ITOPS17:station:0",
            "index": 0,
            "name": "Disponibilité",
            "kind": "rack",
            "description": "Consulter le suivi des services",
            "destination": "itops17_0"
          },
          {
            "id": "ITOPS17:station:1",
            "index": 1,
            "name": "Maintenance",
            "kind": "screens",
            "description": "Consulter le plan de maintenance",
            "destination": "itops17_1"
          },
          {
            "id": "ITOPS17:station:2",
            "index": 2,
            "name": "Sauvegardes",
            "kind": "rack",
            "description": "Examiner les sauvegardes et restaurations",
            "destination": "itops17_2"
          },
          {
            "id": "ITOPS17:station:3",
            "index": 3,
            "name": "Déploiements",
            "kind": "console",
            "description": "Examiner les déploiements",
            "destination": "itops17_3"
          },
          {
            "id": "ITOPS17:station:4",
            "index": 4,
            "name": "Connecteurs",
            "kind": "rack",
            "description": "Consulter le catalogue existant",
            "destination": "connectors"
          }
        ]
      },
      {
        "id": "ACADEMY",
        "level": 3,
        "name": "Académie des agents",
        "description": "Formation et amélioration continue",
        "asset": "room_ACADEMY.webp",
        "stations": [
          {
            "id": "ACADEMY:station:0",
            "index": 0,
            "name": "Simulateur",
            "kind": "globe",
            "description": "Exercice de formation fictif",
            "destination": "training12"
          },
          {
            "id": "ACADEMY:station:1",
            "index": 1,
            "name": "Compétences",
            "kind": "wall",
            "description": "Référentiel des six agents",
            "destination": "skills12"
          },
          {
            "id": "ACADEMY:station:2",
            "index": 2,
            "name": "Atelier pratique",
            "kind": "desk",
            "description": "Exercices et critères",
            "destination": "exercise12"
          },
          {
            "id": "ACADEMY:station:3",
            "index": 3,
            "name": "Bilan pédagogique",
            "kind": "screens",
            "description": "Résultats de la session",
            "destination": "trainingReport12"
          },
          {
            "id": "ACADEMY:station:4",
            "index": 4,
            "name": "Archives de formation",
            "kind": "console",
            "description": "Exporter le bilan",
            "destination": "trainingExport12"
          }
        ]
      },
      {
        "id": "ARCHIVES",
        "level": 4,
        "name": "Archives de l’entreprise",
        "description": "Historique et traçabilité",
        "asset": "room_ARCHIVES.webp",
        "stations": [
          {
            "id": "ARCHIVES:station:0",
            "index": 0,
            "name": "Chronologie",
            "kind": "reactor",
            "description": "Historique filtrable",
            "destination": "archive13"
          },
          {
            "id": "ARCHIVES:station:1",
            "index": 1,
            "name": "Dossiers de missions",
            "kind": "wall",
            "description": "Échanges du scénario",
            "destination": "archive13"
          },
          {
            "id": "ARCHIVES:station:2",
            "index": 2,
            "name": "Archives pédagogiques",
            "kind": "desk",
            "description": "Bilan de formation",
            "destination": "trainingReport13"
          },
          {
            "id": "ARCHIVES:station:3",
            "index": 3,
            "name": "Données importées",
            "kind": "screens",
            "description": "Consulter un instantané externe",
            "destination": "sync13"
          },
          {
            "id": "ARCHIVES:station:4",
            "index": 4,
            "name": "Export des archives",
            "kind": "console",
            "description": "Télécharger l’historique",
            "destination": "archiveExport13"
          }
        ]
      }
    ]
  }
];
