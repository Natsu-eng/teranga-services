"""Accès données pour le référentiel des métiers (`trade`)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade


async def list_active_trades(session: AsyncSession) -> list[Trade]:
    result = await session.execute(
        select(Trade).where(Trade.is_active.is_(True)).order_by(Trade.sort_order, Trade.code)
    )
    return list(result.scalars().all())
