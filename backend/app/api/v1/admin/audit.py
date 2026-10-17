"""/api/v1/admin — Journal d'audit, en lecture seule (ajout seul garanti par la base).

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
from app.models.enums import AuditAction, AuditTargetType, Role
from app.models.user import User
from app.schemas.audit import AuditEntryOut
from app.schemas.pagination import Page
from app.services import audit as audit_service

router = APIRouter()


@router.get("/audit", response_model=Page[AuditEntryOut])
async def list_audit_entries(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    action: Annotated[AuditAction | None, Query()] = None,
    target_type: Annotated[AuditTargetType | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AuditEntryOut]:
    """Journal d'audit, du plus récent au plus ancien. LECTURE SEULE : aucune
    route ne modifie ni ne supprime une entrée (et la base le refuse)."""
    return await audit_service.list_entries(
        session,
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_id=actor_id,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )
