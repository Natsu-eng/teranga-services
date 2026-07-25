"""Accès données pour le référentiel des métiers (`trade`)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade


async def list_active_trades(session: AsyncSession) -> list[Trade]:
    result = await session.execute(
        select(Trade).where(Trade.is_active.is_(True)).order_by(Trade.sort_order, Trade.code)
    )
    return list(result.scalars().all())


async def get_active_trade_by_code(session: AsyncSession, code: str) -> Trade | None:
    """Utilisé par `app.services.ai_triage` pour valider qu'un `trade_code`
    renvoyé par un fournisseur IA correspond à un métier réel et actif avant
    de le renvoyer au client (BUILD_PLAN.md §6 Lot 11)."""
    result = await session.execute(
        select(Trade).where(Trade.code == code, Trade.is_active.is_(True))
    )
    return result.scalar_one_or_none()
