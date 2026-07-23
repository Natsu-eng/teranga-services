# Téranga Services

Plateforme sénégalaise de mise en relation entre particuliers et artisans qualifiés (plomberie, électricité, climatisation, etc.).

## Fonctionnalités

- **Recherche & découverte** — recherche filtrée d'artisans par métier, note et disponibilité.
- **Diagnostic assisté par IA** — description d'un problème (texte, photo, vocal) analysée via Gemini, avec repli automatique sur une heuristique par mots-clés si aucune clé API n'est configurée.
- **Messagerie & devis** — chat client ↔ artisan avec envoi et acceptation de devis.
- **Tableau de bord artisan** — suivi des revenus, des demandes entrantes et des indicateurs de performance.
- **Profils** — fiches artisan détaillées (avis, réalisations, statistiques) et profil client avec moyens de paiement locaux (Wave, Orange Money, carte).

## Topologie

Monorepo à deux services indépendants, chacun avec son propre cycle de build, ses propres dépendances et sa propre porte de qualité :

| Service | Rôle | Stack |
| --- | --- | --- |
| [`frontend/`](frontend/) | Application web (SPA) | React 19, TypeScript, Tailwind CSS v4, Vite |
| [`backend/`](backend/) | API métier | Python, FastAPI, SQLAlchemy async, PostgreSQL (PostGIS à venir) |

Base de données **PostgreSQL** partagée par le backend (Postgres local en dev, Railway en prod — voir [BUILD_PLAN.md](BUILD_PLAN.md)).

Aujourd'hui, le frontend embarque encore un petit serveur Express (`frontend/server.ts`) qui sert le build de production et expose l'unique endpoint IA (`/api/analyze-problem`). C'est une étape transitoire : ce endpoint migre vers FastAPI et Express disparaît une fois la bascule terminée (voir la séquence de lots dans BUILD_PLAN.md).

## Structure du dépôt

```text
teranga-services/
├── README.md          # ce fichier : présentation, topologie
├── BUILD_PLAN.md       # document de référence Phase 2 (backend, données, API)
├── AUDIT.md             # audit historique
├── frontend/             # application web — voir frontend/README.md
└── backend/              # API FastAPI — voir backend/README.md
```

## Documentation par service

- [frontend/README.md](frontend/README.md) — prérequis, installation, scripts, variables d'environnement.
- [backend/README.md](backend/README.md) — prérequis, base de données locale, installation, migrations, lancement du serveur, porte de validation.
- [BUILD_PLAN.md](BUILD_PLAN.md) — décisions d'architecture, modèle de données, contrats d'API, séquence des lots de la Phase 2.
