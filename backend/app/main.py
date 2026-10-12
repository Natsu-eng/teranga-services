from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.security_headers import SecurityHeadersMiddleware
from app.services.storage import resolve_local_dir

settings = get_settings()
configure_logging(settings)

# Documentation interactive (/docs, /redoc, /openapi.json) : outil de
# développement. Désactivée en production -- la carte complète de l'API
# n'a pas à être publiée, et ses scripts tiers n'ont rien à faire sur le
# domaine de production.
_docs_enabled = not settings.is_production
app = FastAPI(
    title="Téranga Services API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
register_exception_handlers(app)

# Origines lues depuis CORS_ORIGINS (backend/.env) — jamais de wildcard "*"
# en dur : en local, seul le frontend Vite explicitement listé est autorisé.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Ajouté en dernier, donc le plus à l'extérieur : les en-têtes de sécurité
# s'appliquent à toute réponse, préflights CORS et erreurs comprises.
app.add_middleware(
    SecurityHeadersMiddleware, production=settings.is_production, docs_enabled=_docs_enabled
)

app.include_router(v1_router, prefix="/api/v1")

# Seul répertoire servi statiquement -- exclusivement les avatars (données
# publiques), jamais STORAGE_LOCAL_DIR (documents de vérification, privés).
# Créé eagerly : StaticFiles exige que le dossier existe au montage.
_avatar_dir = resolve_local_dir(settings.avatar_storage_local_dir)
_avatar_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/avatars", StaticFiles(directory=_avatar_dir), name="avatars")
