from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings)

app = FastAPI(title="Téranga Services API")

app.include_router(v1_router, prefix="/api/v1")
