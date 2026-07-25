"""Tests de `app.services.commission.resolve_effective_commission_rate`
(BUILD_PLAN.md §2.2, §7 -- résolution du taux de commission en vigueur).

Le taux global (`trade_id IS NULL`) est toujours obtenu via
`scripts.seed._seed_default_commission_rate` (get-or-create, idempotent) --
jamais créé manuellement ici : la base de dev exerçée par `db_session` peut
déjà porter le taux global semé par `scripts/seed.py`, et une deuxième ligne
`trade_id=None` avec une plage active se heurterait à la contrainte
d'exclusion de `commission_rate` (BUILD_PLAN.md §2.2). Seules les lignes
scopées à un `trade_id` frais (propre à chaque test) sont créées directement.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commission import CommissionRate
from app.services.commission import (
    CommissionRateIntrouvableError,
    resolve_effective_commission_rate,
)
from scripts.seed import _seed_default_commission_rate
from tests.factories import make_commission_rate, make_trade

FAR_PAST = datetime(2000, 1, 1, tzinfo=UTC)


async def test_trade_specific_rate_overrides_global_rate_when_both_active(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    await _seed_default_commission_rate(db_session)
    specific_rate = await make_commission_rate(db_session, rate_bps=500, trade_id=trade.id)

    resolved = await resolve_effective_commission_rate(db_session, trade_id=trade.id)

    assert resolved.id == specific_rate.id
    assert resolved.rate_bps == 500


async def test_falls_back_to_global_rate_when_no_trade_specific_rate_exists(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    global_rate = await _seed_default_commission_rate(db_session)

    resolved = await resolve_effective_commission_rate(db_session, trade_id=trade.id)

    assert resolved.id == global_rate.id
    assert resolved.trade_id is None


async def test_selects_the_currently_active_rate_among_historical_overlapping_ones(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    now = datetime.now(UTC)
    closed_rate = CommissionRate(
        rate_bps=1500,
        trade_id=trade.id,
        effective_from=now - timedelta(days=10),
        effective_to=now - timedelta(days=5),
    )
    active_rate = CommissionRate(
        rate_bps=800, trade_id=trade.id, effective_from=now - timedelta(days=5)
    )
    db_session.add_all([closed_rate, active_rate])
    await db_session.flush()

    resolved = await resolve_effective_commission_rate(db_session, trade_id=trade.id, at=now)

    assert resolved.id == active_rate.id
    assert resolved.rate_bps == 800


async def test_trade_specific_rate_not_yet_effective_falls_back_to_global(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    global_rate = await _seed_default_commission_rate(db_session)
    future_specific_rate = CommissionRate(
        rate_bps=200, trade_id=trade.id, effective_from=datetime.now(UTC) + timedelta(days=1)
    )
    db_session.add(future_specific_rate)
    await db_session.flush()

    resolved = await resolve_effective_commission_rate(db_session, trade_id=trade.id)

    assert resolved.id == global_rate.id


async def test_raises_when_no_rate_is_in_effect_at_the_given_date(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    await make_commission_rate(db_session, rate_bps=1000, trade_id=trade.id)

    with pytest.raises(CommissionRateIntrouvableError):
        await resolve_effective_commission_rate(db_session, trade_id=trade.id, at=FAR_PAST)
