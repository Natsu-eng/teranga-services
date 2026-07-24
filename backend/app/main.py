from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

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
