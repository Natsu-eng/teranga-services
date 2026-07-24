"""Le nombre de requêtes SQL pour une liste d'artisans ne doit pas croître
avec N (BUILD_PLAN.md §4, §6 Lot 9) -- selectinload/joinedload évitent le
N+1 sur les métiers et vérifications de chaque artisan ; ce test empêche la
dette de performance de s'installer silencieusement dans un futur commit.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.trade import Trade
from app.services.artisans import list_artisans
from tests._sql_query_counter import count_queries
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_trade,
    make_verification,
)

SETTINGS = get_settings()


async def _make_artisans(session: AsyncSession, trade: Trade, n: int) -> None:
    for _ in range(n):
        artisan = await make_artisan_profile(session)
        await make_artisan_trade(session, artisan=artisan, trade=trade)
        await make_verification(session, artisan=artisan)


async def _list(session: AsyncSession, trade: Trade) -> None:
    await list_artisans(
        session,
        trade=trade.code,
        near=None,
        radius_m=None,
        min_rating=None,
        available=None,
        q=None,
        sort=None,
        page=1,
        page_size=50,
        settings=SETTINGS,
    )


async def test_query_count_stays_constant_as_artisan_count_grows(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    await _make_artisans(db_session, trade, 3)

    with count_queries(db_session) as small_queries:
        await _list(db_session, trade)

    await _make_artisans(db_session, trade, 6)  # 9 artisans au total

    with count_queries(db_session) as large_queries:
        await _list(db_session, trade)

    assert len(small_queries) > 0
    assert len(small_queries) == len(large_queries)
