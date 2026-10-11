"""Endpoints /api/v1/admin (BUILD_PLAN.md, espace admin).

Toutes les routes exigent le rôle admin (`require_role(Role.ADMIN)`, même
dépendance que le reste de l'API, Lot 8) -- jamais atteignables autrement
(BUILD_PLAN.md §4 : `scripts/create_admin.py` est le SEUL chemin vers ce
rôle, aucun endpoint ne l'attribue). Un client/artisan reçoit 403
ROLE_INSUFFISANT, un anonyme 401 NON_AUTHENTIFIE -- exactement les mêmes
erreurs génériques que n'importe quelle autre route protégée par rôle
ailleurs dans l'API, sans détail qui distinguerait une route admin d'une
autre pour un tiers non autorisé.
"""

import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider, require_role
from app.core.config import Settings, get_settings
from app.db.session import SessionFactory, get_session, get_session_factory
from app.models.enums import Role, VerificationStatus
from app.models.user import User
from app.schemas.admin import (
    AdminArtisanDetailOut,
    AdminVerificationListItemOut,
    VerificationRejectIn,
    VerificationReviewOut,
)
from app.schemas.interventions import InterventionOut
from app.schemas.pagination import Page
from app.schemas.payments import DisputeResolveIn
from app.services import admin_verification as admin_verification_service
from app.services import interventions as interventions_service
from app.services import payments as payments_service
from app.services.file_validation import MIME_BY_TYPE
from app.services.payment_providers.base import PaymentProvider
from app.services.storage import get_storage_backend

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/verifications", response_model=Page[AdminVerificationListItemOut])
async def list_verifications(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[
        VerificationStatus | None, Query(description="Filtre par statut")
    ] = VerificationStatus.PENDING,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminVerificationListItemOut]:
    return await admin_verification_service.list_pending_verifications(
        session,
        status=status,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/verifications/{verification_id}/content")
async def get_verification_content(
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> StreamingResponse:
    content, detected = await admin_verification_service.get_verification_content(
        session, verification_id=verification_id, storage=get_storage_backend(settings)
    )
    return StreamingResponse(io.BytesIO(content), media_type=MIME_BY_TYPE[detected])


@router.post("/verifications/{verification_id}/approve", response_model=VerificationReviewOut)
async def approve_verification(
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> VerificationReviewOut:
    result = await admin_verification_service.approve_verification(
        session, admin=admin, verification_id=verification_id, settings=settings
    )
    await session.commit()
    return result


@router.post("/verifications/{verification_id}/reject", response_model=VerificationReviewOut)
async def reject_verification(
    verification_id: uuid.UUID,
    payload: VerificationRejectIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> VerificationReviewOut:
    result = await admin_verification_service.reject_verification(
        session,
        admin=admin,
        verification_id=verification_id,
        note=payload.note,
        settings=settings,
    )
    await session.commit()
    return result


@router.get("/artisans/{artisan_id}", response_model=AdminArtisanDetailOut)
async def get_artisan(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


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
    return await interventions_service.list_disputes(
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
    result = await interventions_service.resolve_dispute(
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
    await payments_service.dispatch_payout(
        session_factory, result.payout_id, provider=provider, settings=settings
    )
    return await interventions_service.get_intervention_for_admin(
        session, intervention_id=intervention_id
    )
