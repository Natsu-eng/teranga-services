# Téranga Services

Plateforme sénégalaise de mise en relation entre particuliers et artisans qualifiés (plomberie, électricité, climatisation, etc.).

## Fonctionnalités

- **Recherche & découverte** — recherche filtrée d'artisans par métier, note et disponibilité.
- **Diagnostic assisté par IA** — description d'un problème analysée côté backend (`POST /api/v1/ai/analyze`, Mistral), avec repli automatique sur une heuristique par mots-clés au moindre incident (clé absente ou refusée, timeout, réponse non conforme).
- **Messagerie & devis** — discussion client ↔ artisan en temps réel (WebSocket, repli automatique sur relecture REST), ouverte avec chaque mise en relation ; numéros et e-mails masqués automatiquement, photos réencodées sans métadonnées et visibles des deux seuls participants. Devis envoyés et acceptés depuis la mise en relation.
- **Paiement sécurisé** — séquestre en ligne (Wave, Orange Money, carte) : le client paie le prix du devis sans frais ajoutés, Téranga conserve l'argent jusqu'à sa confirmation de fin des travaux, puis verse à l'artisan son net (commission de 10 % au taux figé, affichée des deux côtés) ; espèces enregistrées ; annulation remboursée, litige arbitré. Fournisseur interchangeable (sandbox en dev).
- **Tableau de bord artisan** — suivi des revenus, des demandes entrantes et des indicateurs de performance.
- **Profils** — fiches artisan détaillées (photo de profil et de couverture envoyées par l'artisan, avis, réalisations, statistiques) et profil client (historique des paiements).
- **Onboarding & vérification artisan** — profil, métiers, photos et documents de vérification (CNI, selfie) en un seul parcours, revus par un espace admin dédié.
- **Back-office admin** — vue d'ensemble aux chiffres réels, vérifications, artisans (suspension réversible), utilisateurs (rôle admin avec anti-verrouillage : jamais soi-même, jamais le dernier), modération des avis signalés, litiges, grille de commission en ajout seul (les taux figés ne bougent jamais) et journal d'audit en ajout seul, garanti par la base.

## Topologie

Monorepo à deux services indépendants, chacun avec son propre cycle de build, ses propres dépendances et sa propre porte de qualité :

| Service | Rôle | Stack |
| --- | --- | --- |
| [`frontend/`](frontend/) | Application web (SPA) | React 19, TypeScript, Tailwind CSS v4, Vite |
| [`backend/`](backend/) | API métier | Python, FastAPI, SQLAlchemy async, PostgreSQL + PostGIS |

Base de données **PostgreSQL** partagée par le backend (Postgres local en dev, Railway en prod — voir [BUILD_PLAN.md](BUILD_PLAN.md)).

**Mise en production** : runbook complet dans [DEPLOYMENT.md](DEPLOYMENT.md) (Railway : backend Docker, front statique, PostgreSQL + PostGIS, Redis, stockage R2/S3 ; variables, étapes, durcissement). Points à lire en premier : fournisseur SMS réel encore à brancher (bloquant), PostGIS à vérifier sur Railway, stockage objet obligatoire (disque éphémère).

Le frontend est un projet **Vite pur** : en dev, le serveur Vite proxifie `/api/v1/*` vers FastAPI ; en production, `vite build` produit des fichiers statiques servis par l'hébergeur (Vercel), qui appellent directement l'API (`VITE_API_BASE_URL`). Aucun serveur Node côté front, aucun secret dans le front : l'IA, l'auth et toutes les clés vivent dans le backend. L'ancien serveur Express (`frontend/server.ts`) et son endpoint Gemini ont été retirés au Lot 13.

**Lancer en local** : deux terminaux — `cd backend && uv run uvicorn app.main:app --reload --port 8000`, puis `cd frontend && npm run dev` (<http://localhost:3000>). Détail : [frontend/README.md](frontend/README.md#développement-local--lancer-les-deux-services).

## Structure du dépôt

```text
teranga-services/
├── README.md          # ce fichier : présentation, topologie
├── BUILD_PLAN.md       # document de référence Phase 2 (backend, données, API)
├── AUDIT.md             # audit historique
├── AUDIT_PHASE2.md      # audit Phase 2, journal des lots livrés
├── DEPLOYMENT.md        # runbook de mise en production (Railway)
├── docker-compose.dev.yml # facultatif : vrai Redis + MinIO (S3) pour essai local
├── frontend/             # application web — voir frontend/README.md
└── backend/              # API FastAPI — voir backend/README.md
```

## Documentation par service

- [frontend/README.md](frontend/README.md) — prérequis, installation, scripts, variables d'environnement.
- [backend/README.md](backend/README.md) — prérequis, base de données locale, installation, migrations, lancement du serveur, porte de validation.
- [BUILD_PLAN.md](BUILD_PLAN.md) — décisions d'architecture, modèle de données, contrats d'API, séquence des lots de la Phase 2.
