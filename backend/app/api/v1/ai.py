"""Endpoint `/api/v1/ai/analyze` (BUILD_PLAN.md §3.2, §6 Lot 11).

**Public, non authentifié** : l'écran `/demande` (DescribeProblemScreen) du
front est accessible sans connexion (il n'est pas derrière `ProtectedRoute`,
voir frontend/src/App.tsx) -- exiger une authentification sur ce lot
casserait ce parcours existant. La protection contre l'abus (chaque appel
routé vers un fournisseur réseau coûte potentiellement de l'argent réel)
passe donc par un rate limiting par IP, même mécanisme que
`POST /auth/request-otp` (fenêtre glissante en mémoire,
app/services/rate_limit.py) -- voir `get_ai_analyze_rate_limiter`.

Toute la validation/durcissement de la sortie IA (schéma, montants,
existence du métier) vit dans `app.services.ai_triage` ; cet endpoint ne
fait que router la requête et appliquer le rate limit.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.schemas.ai_triage import AnalyzeProblemIn, TriageResult
from app.services import ai_triage as ai_triage_service
from app.services.rate_limit import RateLimiter, get_ai_analyze_rate_limiter

router = APIRouter(prefix="/ai", tags=["ai"])


class TropDeDemandesIaError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop de demandes d'analyse IA, merci de réessayer plus tard.",
            status_code=429,
        )


@router.post("/analyze", response_model=TriageResult)
async def analyze(
    payload: AnalyzeProblemIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiter, Depends(get_ai_analyze_rate_limiter)],
) -> TriageResult:
    allowed = await rate_limiter.check(
        f"ip:{client_ip(request, settings)}",
        max_hits=settings.rate_limit_ai_analyze_per_ip_max,
        window_seconds=settings.rate_limit_ai_analyze_per_ip_window_seconds,
    )
    if not allowed:
        raise TropDeDemandesIaError()

    return await ai_triage_service.analyze_problem(session, payload.description, settings=settings)
