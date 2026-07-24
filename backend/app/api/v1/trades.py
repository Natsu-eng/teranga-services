"""Endpoint /api/v1/trades (BUILD_PLAN.md §3.2, §6 Lot 9).

Référentiel des métiers actifs, pour les filtres du front. Lecture publique,
pas de pagination (liste courte par construction).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.trades import TradeOut
from app.services import trades as trades_service

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("", response_model=list[TradeOut])
async def list_trades(session: Annotated[AsyncSession, Depends(get_session)]) -> list[TradeOut]:
    return await trades_service.list_active_trades(session)
