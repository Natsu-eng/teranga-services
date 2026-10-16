"""/api/v1/admin — Gestion des artisans : liste, fiche complète, suspension et réactivation.

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin import (
    AdminArtisanDetailOut,
    AdminArtisanListItemOut,
    ArtisanReactivateIn,
    ArtisanSuspendIn,
)
from app.schemas.pagination import Page
from app.services import admin_artisans as admin_artisans_service
from app.services import admin_verification as admin_verification_service

router = APIRouter()


@router.get("/artisans", response_model=Page[AdminArtisanListItemOut])
async def list_artisans(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[
        Literal["none", "pending", "verified", "rejected", "suspended"] | None,
        Query(description="Statut de vérification, ou « suspended »"),
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="Nom ou téléphone")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminArtisanListItemOut]:
    """Tous les artisans, vérifiés ou non, suspendus compris."""
    return await admin_artisans_service.list_artisans(
        session,
        status=status,
        q=q,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/artisans/{artisan_id}/suspend", response_model=AdminArtisanDetailOut)
async def suspend_artisan(
    artisan_id: uuid.UUID,
    payload: ArtisanSuspendIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    """Suspend un artisan : invisible en recherche, inéligible aux NOUVELLES
    demandes ; ses interventions et paiements en cours continuent. Journalisé."""
    await admin_artisans_service.suspend_artisan(
        session, admin=admin, artisan_id=artisan_id, reason=payload.reason
    )
    await session.commit()
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


@router.post("/artisans/{artisan_id}/reactivate", response_model=AdminArtisanDetailOut)
async def reactivate_artisan(
    artisan_id: uuid.UUID,
    payload: ArtisanReactivateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    """Lève la suspension (motif facultatif). Journalisé."""
    await admin_artisans_service.reactivate_artisan(
        session, admin=admin, artisan_id=artisan_id, note=payload.note
    )
    await session.commit()
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


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
