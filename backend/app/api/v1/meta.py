"""Endpoint /api/v1/meta : informations publiques sur l'instance.

Lecture publique, sans authentification : sert au front à savoir s'il tourne
sur une instance de test (bandeau « Version de test », transparence beta).
N'expose qu'un environnement et un booléen, jamais un réglage secret.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.meta import MetaOut
from app.services.otp_test_mode import is_test_mode_enabled

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("", response_model=MetaOut)
async def instance_meta(settings: Annotated[Settings, Depends(get_settings)]) -> MetaOut:
    return MetaOut(
        environment=settings.environment,
        otp_test_mode=is_test_mode_enabled(settings),
    )
