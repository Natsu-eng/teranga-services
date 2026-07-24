# Téranga Services — Backend

API métier de Téranga Services (FastAPI). C'est le service `backend/` du monorepo — voir le [README racine](../README.md) pour la présentation du produit et la topologie complète (frontend + backend).

Pas encore de modèle métier à ce stade (Lot 6 — socle uniquement) : ce service expose un squelette FastAPI qui démarre, se connecte à Postgres, migre son schéma via Alembic, et a sa propre porte de qualité.

## Stack technique

| Domaine | Choix |
| --- | --- |
| Langage | Python 3.12+ |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.x (mode async, driver `asyncpg`) |
| Migrations | Alembic (async) |
| Config | Pydantic v2 + pydantic-settings |
| Dépendances | [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) |
| Qualité | ruff (lint + format), mypy (strict), pytest + pytest-asyncio + httpx |

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL en local (aucune valeur de connexion n'est fournie par défaut par l'application)

## Créer la base locale

```bash
createdb teranga
```

(ou l'équivalent via pgAdmin / pratique existante — le nom de la base est libre, il sera renseigné dans `DATABASE_URL`.)

## Installation

Toutes les commandes ci-dessous s'exécutent depuis ce dossier (`backend/`).

1. Copier `.env.example` vers `.env` et renseigner vos propres valeurs (au minimum `DATABASE_URL`) :

   ```bash
   cp .env.example .env
   ```

2. Installer les dépendances (crée `.venv/` automatiquement) :

   ```bash
   uv sync
   ```

## Appliquer les migrations

```bash
uv run alembic upgrade head
```

Pour revenir en arrière d'une révision :

```bash
uv run alembic downgrade -1
```

## Jeu de données de développement

Sème un jeu de données cohérent (métiers, taux de commission par défaut,
les 3 artisans du mock frontend avec de vraies coordonnées à Dakar, des
avis liés à des interventions terminées). Idempotent : relancer la commande
ne duplique rien. **Jamais exécuté automatiquement** — toujours à la main,
après les migrations :

```bash
uv run python scripts/seed.py
```

Détail du contenu semé et des choix de conception : voir l'en-tête de
[scripts/seed.py](scripts/seed.py).

## Lancer le serveur

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- API : <http://localhost:8000>
- Documentation OpenAPI interactive : <http://localhost:8000/docs>
- Liveness : `GET /api/v1/health`
- Readiness (vérifie Postgres) : `GET /api/v1/health/ready`

## Variables d'environnement

| Variable | Requise | Description |
| --- | --- | --- |
| `DATABASE_URL` | Oui | URL de connexion Postgres, driver `asyncpg` obligatoire. Aucune valeur par défaut : le démarrage échoue explicitement si absente ou malformée. |
| `APP_ENV` | Non (`dev`) | `dev` \| `staging` \| `prod`. Contrôle le format des logs (lisible en dev, JSON en prod) et si le provider SMS console journalise le code OTP. |
| `LOG_LEVEL` | Non (`INFO`) | Niveau de log Python standard. |
| `CORS_ORIGINS` | Non (vide) | Origines autorisées, séparées par des virgules. Pas de wildcard. |
| `JWT_SECRET` | Oui | Secret de signature des JWT. Aucune valeur par défaut : le démarrage échoue si absent ou trop court (< 32 caractères). |
| `JWT_ACCESS_TTL_SECONDS` | Non (`900`) | Durée de vie de l'access token (secondes). |
| `JWT_REFRESH_TTL_SECONDS` | Non (`2592000`) | Durée de vie du refresh token (secondes, 30 jours par défaut). |
| `SMS_PROVIDER` | Non (`console`) | `console` \| `unconfigured`. Fournisseur d'envoi des codes OTP -- voir [Authentification](#authentification-téléphone--otp). |
| `PHONE_DEFAULT_REGION` | Non (`SN`) | Région ISO 3166-1 alpha-2 utilisée pour interpréter un numéro écrit sans indicatif. |
| `PHONE_ALLOWED_REGIONS` | Non (`SN`) | Régions dont les numéros sont acceptés, séparées par des virgules. |
| `OTP_CODE_LENGTH` | Non (`6`) | Longueur du code OTP (chiffres). |
| `OTP_TTL_SECONDS` | Non (`300`) | TTL du code OTP (secondes, 5 min par défaut). |
| `OTP_MAX_ATTEMPTS` | Non (`5`) | Tentatives de vérification autorisées avant invalidation du code. |
| `OTP_HASH_ITERATIONS` | Non (`600000`) | Itérations PBKDF2-HMAC-SHA256 pour le hachage du code OTP. |
| `RATE_LIMIT_OTP_PER_PHONE_MAX` | Non (`3`) | Nombre max de `request-otp` par numéro sur la fenêtre glissante. |
| `RATE_LIMIT_OTP_PER_PHONE_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par numéro (secondes). |
| `RATE_LIMIT_OTP_PER_IP_MAX` | Non (`10`) | Nombre max de `request-otp` par IP sur la fenêtre glissante. |
| `RATE_LIMIT_OTP_PER_IP_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par IP (secondes). |
| `ARTISAN_SEARCH_DEFAULT_RADIUS_M` | Non (`10000`) | Rayon de recherche par défaut (mètres) si `radius_m` n'est pas fourni sur `GET /artisans`. |
| `ARTISAN_SEARCH_MAX_RADIUS_M` | Non (`50000`) | Plafond dur du rayon de recherche (mètres). |
| `PAGINATION_PAGE_SIZE_DEFAULT` | Non (`20`) | Taille de page par défaut, réutilisée par `GET /artisans` et `GET /artisans/{id}/reviews`. |
| `PAGINATION_PAGE_SIZE_MAX` | Non (`50`) | Plafond de taille de page. |
| `PAGINATION_MAX_PAGE` | Non (`50`) | Page maximale autorisée -- au-delà, `422 PAGE_HORS_BORNES`. |
| `VERIFICATION_REQUIRED_DOC_TYPES` | Non (`cni,selfie`) | Types de documents requis pour `verified_status=VERIFIED`, séparés par des virgules. |

Voir [.env.example](.env.example) pour le détail documenté de chaque variable.

## Authentification (téléphone + OTP)

Flux : `POST /api/v1/auth/request-otp` (toujours 204, non énumérant) →
`POST /api/v1/auth/verify-otp` (crée le compte au premier login, renvoie
`{ access, refresh, user }`) → requêtes authentifiées via
`Authorization: Bearer <access>`. `POST /api/v1/auth/refresh` fait tourner
la session (rotation, l'ancien refresh est révoqué) ; `POST /auth/logout`
et `POST /auth/logout-all` révoquent respectivement une session ou toutes.
Détail complet des garde-fous de sécurité : [BUILD_PLAN.md §4](../BUILD_PLAN.md#4-authentification-téléphone--otp).

**Provider SMS** : `SMS_PROVIDER=console` (défaut, dev) journalise le code
en clair dans les logs -- uniquement si `APP_ENV=dev` (vérifié deux fois :
au choix du provider *et* dans le provider lui-même, pour ne jamais faire
fuiter un code hors dev même mal configuré). Aucun fournisseur SMS
commercial n'est branché à ce stade ; ce choix reste à trancher avant la
mise en production (`SMS_PROVIDER=unconfigured` échoue explicitement en
attendant).

**Rate limiting** sur `request-otp` : fenêtre glissante **en mémoire**
(`app/services/rate_limit.py`), par numéro et par IP. Dette technique
documentée : cet état est local au processus, il ne survit ni à un
redémarrage ni à plusieurs instances/workers -- à remplacer par un backend
partagé (Redis, ou une table dédiée) si le trafic ou le nombre d'instances
grandit.

## Lecture des artisans (recherche géo, avis, stats)

`GET /api/v1/artisans` (proximité PostGIS, filtres `trade`/`min_rating`/
`available`/`q`, tri `distance`/`rating`/`recent`, pagination), `GET
/api/v1/artisans/{id}` (profil détaillé), `GET /api/v1/artisans/{id}/reviews`
(avis publiés), `GET /api/v1/artisans/{id}/stats` (indicateurs de réputation
publics ; revenus réservés au propriétaire ou à un admin authentifié), `GET
/api/v1/trades` (référentiel des métiers). Aucune authentification requise
sauf pour la vue enrichie de `/stats`. Détail complet (combinaison rayon
client/zone artisan, stratégie de pagination, règle de dérivation de
`verified_status`) : [BUILD_PLAN.md §5](../BUILD_PLAN.md#5-architecture-géo-postgis)
et [§2.2](../BUILD_PLAN.md#22-tables).

**Architecture en couches** (`app/api/v1/`, `app/services/`,
`app/repositories/`, `app/schemas/`) instaurée sur ce lot, appliquée à
`trades` et `artisans` -- gabarit pour le reste du projet. `app/api/v1/auth.py`
n'a volontairement pas été réaligné dessus (flux déjà propre et testé,
réalignement recommandé dans un lot dédié séparé si souhaité).

## Porte de validation

Commande unique (ruff check, ruff format --check, mypy strict, pytest) :

```bash
uv run python scripts/validate.py
```
