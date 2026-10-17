"""/api/v1/admin — Rôle administrateur : liste des comptes, octroi et retrait (anti-verrouillage).

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
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin import (
    AdminRoleChangeIn,
    AdminUserOut,
)
from app.schemas.pagination import Page
from app.services import admin_users as admin_users_service

router = APIRouter()


@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    q: Annotated[str | None, Query(max_length=100, description="Nom ou téléphone")] = None,
    role: Annotated[Role | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminUserOut]:
    return await admin_users_service.list_users(
        session,
        viewer=admin,
        q=q,
        role=role,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/users/{user_id}/grant-admin", response_model=AdminUserOut)
async def grant_admin(
    user_id: uuid.UUID,
    payload: AdminRoleChangeIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminUserOut:
    """Promeut un compte CLIENT dédié au rôle admin. Journalisé."""
    target = await admin_users_service.grant_admin(
        session, admin=admin, user_id=user_id, note=payload.note
    )
    await session.commit()
    return await admin_users_service.get_user(session, viewer=admin, user_id=target.id)


@router.post("/users/{user_id}/revoke-admin", response_model=AdminUserOut)
async def revoke_admin(
    user_id: uuid.UUID,
    payload: AdminRoleChangeIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminUserOut:
    """Retire le rôle admin (jamais le sien, jamais le dernier). Journalisé."""
    target = await admin_users_service.revoke_admin(
        session, admin=admin, user_id=user_id, note=payload.note
    )
    await session.commit()
    return await admin_users_service.get_user(session, viewer=admin, user_id=target.id)
