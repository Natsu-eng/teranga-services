"""Contraintes réelles du schéma des paiements (migration b25862fcd340).

Exercées contre Postgres (pas de mock) : ce sont elles qui garantissent les
invariants financiers même si un futur code applicatif se trompait -- deux
requêtes simultanées comprises.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PayoutChannel,
    PlatformFeeKind,
    PlatformFeeStatus,
    Role,
)
from app.models.intervention import InterventionDispute
from app.models.payment import Payment, PaymentEvent, Payout, PlatformFee
from tests.factories import make_engagement, make_payment


async def test_a_single_live_payment_per_intervention(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    await make_payment(
        db_session,
        intervention=engagement.intervention,
        amount_fcfa=12_000,
        status=PaymentStatus.EN_ATTENTE,
    )

    with pytest.raises(IntegrityError, match="uq_payment_active_intervention_id"):
        await make_payment(
            db_session,
            intervention=engagement.intervention,
            amount_fcfa=12_000,
            status=PaymentStatus.RETENU,
        )


async def test_an_abandoned_checkout_frees_the_place(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    for status in (PaymentStatus.ECHOUE, PaymentStatus.ANNULE, PaymentStatus.REMBOURSE):
        await make_payment(
            db_session, intervention=engagement.intervention, amount_fcfa=12_000, status=status
        )

    live = await make_payment(
        db_session,
        intervention=engagement.intervention,
        amount_fcfa=12_000,
        status=PaymentStatus.EN_ATTENTE,
    )

    assert live.id is not None


async def test_cash_never_has_a_provider(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    db_session.add(
        Payment(
            intervention_id=engagement.intervention.id,
            amount_fcfa=12_000,
            channel=PaymentChannel.CASH,
            status=PaymentStatus.REUSSI,
            provider="sandbox",
        )
    )

    with pytest.raises(IntegrityError, match="ck_payment_provider_iff_online_channel"):
        await db_session.flush()


async def test_online_payment_always_has_a_provider(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    db_session.add(
        Payment(
            intervention_id=engagement.intervention.id,
            amount_fcfa=12_000,
            channel=PaymentChannel.WAVE,
            status=PaymentStatus.EN_ATTENTE,
        )
    )

    with pytest.raises(IntegrityError, match="ck_payment_provider_iff_online_channel"):
        await db_session.flush()


async def test_a_webhook_event_is_recorded_only_once(db_session: AsyncSession) -> None:
    db_session.add(
        PaymentEvent(
            provider="sandbox", event_id="evt_1", event_type="checkout.completed", outcome="retenu"
        )
    )
    await db_session.flush()
    db_session.add(
        PaymentEvent(
            provider="sandbox", event_id="evt_1", event_type="checkout.completed", outcome="retenu"
        )
    )

    with pytest.raises(IntegrityError, match="uq_payment_event_provider_event_id"):
        await db_session.flush()


async def test_the_same_event_id_from_another_provider_is_distinct(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            PaymentEvent(provider="sandbox", event_id="evt_1", event_type="x", outcome="ignore"),
            PaymentEvent(provider="autre", event_id="evt_1", event_type="x", outcome="ignore"),
        ]
    )

    await db_session.flush()


async def test_a_single_commission_per_intervention(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    for _ in range(2):
        db_session.add(
            PlatformFee(
                intervention_id=engagement.intervention.id,
                kind=PlatformFeeKind.COMMISSION,
                amount_fcfa=1_200,
                commission_rate_id=engagement.intervention.commission_rate_id,
                status=PlatformFeeStatus.DUE,
            )
        )

    with pytest.raises(IntegrityError, match="uq_platform_fee_commission_intervention_id"):
        await db_session.flush()


async def test_a_single_payout_per_intervention(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.TERMINEE)
    for _ in range(2):
        db_session.add(
            Payout(
                artisan_id=engagement.artisan.id,
                intervention_id=engagement.intervention.id,
                amount_fcfa=10_800,
                channel=PayoutChannel.WAVE,
                destination_phone=engagement.artisan_user.phone,
                provider="sandbox",
            )
        )

    with pytest.raises(IntegrityError, match="uq_payout_intervention_id"):
        await db_session.flush()


async def test_cancellation_fields_go_together(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.ANNULEE)
    engagement.intervention.cancelled_at = datetime.now(UTC)

    with pytest.raises(IntegrityError, match="ck_intervention_cancellation_fields_together"):
        await db_session.flush()


async def test_a_dispute_resolution_is_complete_or_absent(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.LITIGE)
    db_session.add(
        InterventionDispute(
            intervention_id=engagement.intervention.id,
            opened_by_id=engagement.client.id,
            opened_by_role=Role.CLIENT,
            reason="Travaux non terminés.",
            resolved_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError, match="ck_intervention_dispute_resolution_fields_together"):
        await db_session.flush()
