"""Données de référence de production (scripts/seed_reference.py) et
refus des données de démonstration en production (scripts/seed.py)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.commission import CommissionRate
from app.models.enums import AuditAction
from app.models.trade import Trade
from app.services.reference_data import TRADES
from scripts import seed as demo_seed
from scripts.seed_reference import seed_reference


async def test_reference_data_is_complete_and_idempotent(db_session: AsyncSession) -> None:
    await seed_reference(db_session, rate_bps=1000)
    second_run = await seed_reference(db_session, rate_bps=1000)

    assert second_run == []  # rien n'est recréé ni modifié
    codes = set((await db_session.execute(select(Trade.code))).scalars())
    assert {code for code, _, _ in TRADES} <= codes
    open_global = (
        (
            await db_session.execute(
                select(CommissionRate).where(
                    CommissionRate.trade_id.is_(None),
                    CommissionRate.tier.is_(None),
                    CommissionRate.effective_to.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(open_global) == 1


async def test_the_initial_rate_is_journaled_and_never_overwrites_one(
    db_session: AsyncSession,
) -> None:
    # Base sans taux global ouvert (dans la transaction du test, annulée).
    await db_session.execute(
        update(CommissionRate)
        .where(
            CommissionRate.trade_id.is_(None),
            CommissionRate.tier.is_(None),
            CommissionRate.effective_to.is_(None),
        )
        .values(effective_to=datetime.now(UTC) - timedelta(seconds=1))
    )

    created = await seed_reference(db_session, rate_bps=0)
    again = await seed_reference(db_session, rate_bps=2500)

    assert "taux de commission global (0 points de base)" in created
    assert again == []  # un taux déjà en place n'est jamais remplacé
    entry = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.COMMISSION_RATE_CREATE)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    assert entry.actor_id is None  # auteur : le script
    assert entry.details["via"] == "scripts/seed_reference.py"
    assert entry.details["rate_bps"] == 0


async def test_demo_seed_refuses_to_run_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_seed, "get_settings", lambda: SimpleNamespace(is_production=True))

    with pytest.raises(SystemExit, match="données de DÉMONSTRATION"):
        await demo_seed.main()
