"""/api/v1/admin — Litiges : file à trancher et arbitrage (versement ou remboursement).

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider, require_role
from app.core.config import Settings, get_settings
from app.db.session import SessionFactory, get_session, get_session_factory
from app.models.enums import Role
from app.models.user import User
from app.schemas.interventions import InterventionOut
from app.schemas.pagination import Page
from app.schemas.payments import DisputeResolveIn
from app.services import disputes as disputes_service
from app.services import interventions as interventions_service
from app.services import payouts as payouts_service
from app.services.payment_providers.base import PaymentProvider

router = APIRouter()


@router.get("/disputes", response_model=Page[InterventionOut])
async def list_disputes(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    resolved: Annotated[bool, Query(description="Litiges déjà tranchés")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[InterventionOut]:
    """Litiges (BUILD_PLAN.md §3.5) : chaque intervention avec son volet
    financier complet (montant retenu, commission, versement) et le motif."""
    return await disputes_service.list_disputes(
        session,
        resolved=resolved,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/disputes/{intervention_id}/resolve", response_model=InterventionOut)
async def resolve_dispute(
    intervention_id: uuid.UUID,
    payload: DisputeResolveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[PaymentProvider | None, Depends(get_payment_provider)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> InterventionOut:
    """Tranche un litige : `libere` (versement à l'artisan) ou `rembourse`
    (client remboursé). `admin` = celui authentifié, jamais un champ."""
    result = await disputes_service.resolve_dispute(
        session,
        intervention_id=intervention_id,
        admin=admin,
        outcome=payload.outcome,
        note=payload.note,
        settings=settings,
        provider=provider,
    )
    await session.commit()
    if result.payout_id is None:
        return result.intervention
    await payouts_service.dispatch_payout(
        session_factory, result.payout_id, provider=provider, settings=settings
    )
    return await interventions_service.get_intervention_for_admin(
        session, intervention_id=intervention_id
    )
