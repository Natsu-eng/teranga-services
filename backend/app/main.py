from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.storage import resolve_local_dir

settings = get_settings()
configure_logging(settings)

app = FastAPI(title="Téranga Services API")
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

app.include_router(v1_router, prefix="/api/v1")

# Seul répertoire servi statiquement -- exclusivement les avatars (données
# publiques), jamais STORAGE_LOCAL_DIR (documents de vérification, privés).
# Créé eagerly : StaticFiles exige que le dossier existe au montage.
_avatar_dir = resolve_local_dir(settings.avatar_storage_local_dir)
_avatar_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/avatars", StaticFiles(directory=_avatar_dir), name="avatars")
