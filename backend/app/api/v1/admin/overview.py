"""/api/v1/admin — Vue d'ensemble : chiffres dérivés des tables métier.

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin_overview import AdminOverviewOut
from app.services import admin_overview as admin_overview_service

router = APIRouter()


@router.get("/overview", response_model=AdminOverviewOut)
async def get_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminOverviewOut:
    """Indicateurs du back-office, tous dérivés des tables métier (zéros
    honnêtes sans données, jamais de chiffre estimé)."""
    return await admin_overview_service.get_overview(session)
