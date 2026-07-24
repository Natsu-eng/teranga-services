"""Logique métier du référentiel des métiers (`GET /api/v1/trades`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import trades as trades_repository
from app.schemas.trades import TradeOut


async def list_active_trades(session: AsyncSession) -> list[TradeOut]:
    trades = await trades_repository.list_active_trades(session)
    return [TradeOut.model_validate(trade) for trade in trades]
