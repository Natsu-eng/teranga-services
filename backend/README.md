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
| `APP_ENV` | Non (`dev`) | `dev` \| `staging` \| `prod`. Contrôle le format des logs (lisible en dev, JSON en prod). |
| `LOG_LEVEL` | Non (`INFO`) | Niveau de log Python standard. |
| `CORS_ORIGINS` | Non (vide) | Origines autorisées, séparées par des virgules. Pas de wildcard. |

Voir [.env.example](.env.example) pour le détail documenté de chaque variable.

## Porte de validation

Commande unique (ruff check, ruff format --check, mypy strict, pytest) :

```bash
uv run python scripts/validate.py
```
