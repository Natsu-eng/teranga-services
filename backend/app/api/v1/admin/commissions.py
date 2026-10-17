"""/api/v1/admin — Grille de commission : consultation et ajout d'un taux daté (jamais d'édition).

Routes déplacées telles quelles depuis l'ancien module unique ; préfixe,
tag et garde `require_role(Role.ADMIN)` inchangés (voir __init__.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin_commission import (
    AdminCommissionRateOut,
    CommissionGridOut,
    CommissionRateCreateIn,
)
from app.services import admin_commission as admin_commission_service

router = APIRouter()


@router.get("/commission-rates", response_model=CommissionGridOut)
async def get_commission_grid(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    trade_code: Annotated[str | None, Query(max_length=50)] = None,
) -> CommissionGridOut:
    """Toute la grille : en vigueur, programmés, archivés, avec le nombre
    d'interventions qui ont figé chaque taux."""
    return await admin_commission_service.get_grid(
        session, trade_code=trade_code, settings=settings
    )


@router.post("/commission-rates", response_model=AdminCommissionRateOut, status_code=201)
async def add_commission_rate(
    payload: CommissionRateCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminCommissionRateOut:
    """AJOUTE un taux daté (jamais d'édition ni de suppression) ; le taux de
    même portée en vigueur se termine où il commence. Les interventions
    existantes gardent leur taux figé. Journalisé."""
    result = await admin_commission_service.create_rate(
        session,
        admin=admin,
        rate_bps=payload.rate_bps,
        trade_code=payload.trade_code,
        tier=payload.tier,
        effective_from=payload.effective_from,
        note=payload.note,
        settings=settings,
    )
    await session.commit()
    return result
