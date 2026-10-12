# Image de production du backend FastAPI (DEPLOYMENT.md).
#
# - uv installe EXACTEMENT les versions de uv.lock (--frozen), sans les
#   dépendances de développement ;
# - image finale minimale, exécutée par un utilisateur non-root ;
# - aucun secret dans l'image : toute la configuration vient des variables
#   d'environnement du service (fail-fast au démarrage en production) ;
# - .dockerignore exclut .env*, var/ (fichiers locaux, dont des documents
#   d'identité de dev) et les tests.

# Python 3.12 sur Debian stable « slim » : les correctifs de sécurité de la
# branche 3.12 sont repris à chaque reconstruction.
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder
# Version de uv figée (reproductibilité), même famille que celle du dev.
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# Dépendances d'abord : cette couche n'est reconstruite que si le verrou change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts

FROM base
RUN useradd --create-home --uid 10001 teranga
WORKDIR /app
COPY --from=builder --chown=teranga:teranga /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER teranga
EXPOSE 8000

# PORT est fourni par la plateforme (Railway) ; 8000 par défaut.
# WEB_CONCURRENCY (workers uvicorn, 1 par défaut) : au-delà de 1, REDIS_URL
# est indispensable (état temps réel partagé entre processus).
# Pas d'en-tête « Server » (version du serveur) ; arrêt gracieux borné.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --no-server-header --timeout-graceful-shutdown 20"]
