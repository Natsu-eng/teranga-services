import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


# GET et HEAD : les sondes de disponibilité (UptimeRobot...) envoient souvent
# HEAD ; uvicorn n'envoie alors pas de corps. HEAD est déclaré à part et hors
# du schéma OpenAPI : une seule route GET + HEAD y produirait deux opérations
# de même identifiant (avertissement de FastAPI).
@router.get("")
@router.head("", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
@router.head("/ready", include_in_schema=False)
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Readiness check failed: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "detail": "La base de données ne répond pas."}
    return {"status": "ok"}
