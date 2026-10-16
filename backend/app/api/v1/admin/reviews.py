"""/api/v1/admin — Modération des avis : liste, masquage motivé, rétablissement.

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import ReviewStatus, Role
from app.models.user import User
from app.schemas.admin import (
    AdminReviewOut,
    ReviewHideIn,
    ReviewRestoreIn,
)
from app.schemas.pagination import Page
from app.services import admin_reviews as admin_reviews_service

router = APIRouter()


@router.get("/reviews", response_model=Page[AdminReviewOut])
async def list_reviews(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[ReviewStatus | None, Query()] = None,
    artisan_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Commentaire ou nom de l'auteur")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminReviewOut]:
    """Avis à modérer : les signalés d'abord, sauf filtre de statut."""
    return await admin_reviews_service.list_reviews(
        session,
        status=status,
        artisan_id=artisan_id,
        q=q,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/reviews/{review_id}/hide", response_model=AdminReviewOut)
async def hide_review(
    review_id: uuid.UUID,
    payload: ReviewHideIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminReviewOut:
    """Masque un avis (motif obligatoire), recalcule la note. Journalisé, réversible."""
    result = await admin_reviews_service.hide_review(
        session, admin=admin, review_id=review_id, reason=payload.reason
    )
    await session.commit()
    return result


@router.post("/reviews/{review_id}/restore", response_model=AdminReviewOut)
async def restore_review(
    review_id: uuid.UUID,
    payload: ReviewRestoreIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminReviewOut:
    """Rétablit un avis masqué, ou maintient un avis signalé. Recalcule la
    note. Journalisé."""
    result = await admin_reviews_service.restore_review(
        session, admin=admin, review_id=review_id, note=payload.note
    )
    await session.commit()
    return result
