"""/api/v1/admin — Revue des documents de vérification des artisans : file d'attente, contenu
(réservé à l'admin), approbation et rejet motivé.

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import Role, VerificationStatus
from app.models.user import User
from app.schemas.admin import (
    AdminVerificationListItemOut,
    VerificationRejectIn,
    VerificationReviewOut,
)
from app.schemas.pagination import Page
from app.services import admin_verification as admin_verification_service
from app.services.file_validation import MIME_BY_TYPE
from app.services.storage import get_storage_backend

router = APIRouter()


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
