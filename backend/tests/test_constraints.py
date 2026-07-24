"""Contraintes CHECK et d'exclusion effectivement rejetantes."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commission import CommissionRate
from app.models.enums import PaymentChannel, PaymentStatus, Role
from app.models.intervention import Quote
from app.models.payment import Payment
from app.models.review import Review
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_service_request,
    make_trade,
    make_user,
)


async def test_review_rating_must_be_between_1_and_5(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan_profile = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    service_request = await make_service_request(db_session, client=client, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client,
        artisan=artisan_profile,
        commission_rate=commission_rate,
    )

    db_session.add(
        Review(
            intervention_id=intervention.id,
            author_id=client.id,
            artisan_id=artisan_profile.id,
            rating=6,
            comment="Note hors bornes.",
            contact_verified=True,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_payment_amount_cannot_be_negative(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan_profile = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    service_request = await make_service_request(db_session, client=client, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client,
        artisan=artisan_profile,
        commission_rate=commission_rate,
    )

    db_session.add(
        Payment(
            intervention_id=intervention.id,
            amount_fcfa=-1,
            channel=PaymentChannel.CASH,
            status=PaymentStatus.EN_ATTENTE,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_quote_total_must_equal_labor_plus_materials(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan_profile = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    service_request = await make_service_request(db_session, client=client, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client,
        artisan=artisan_profile,
        commission_rate=commission_rate,
    )

    db_session.add(
        Quote(
            intervention_id=intervention.id,
            labor_fcfa=8_000,
            materials_fcfa=4_000,
            total_fcfa=13_000,  # incohérent : devrait être 12 000
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_commission_rate_bps_must_be_between_0_and_10000(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    db_session.add(
        CommissionRate(rate_bps=10_001, trade_id=trade.id, effective_from=datetime.now(UTC))
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_commission_rate_cannot_overlap_for_same_trade_and_tier(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    await make_commission_rate(db_session, trade_id=trade.id, rate_bps=1000)

    # Même trade_id, même tier (NULL), plage de dates chevauchante (les deux
    # sont "en vigueur" -- effective_to NULL).
    db_session.add(
        CommissionRate(rate_bps=1200, trade_id=trade.id, effective_from=datetime.now(UTC))
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
