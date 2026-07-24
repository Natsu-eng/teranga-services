"""Règle métier « avis conditionné » : garde applicative + trigger DB."""

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InterventionStatus, Role
from app.models.intervention import Intervention
from app.models.review import Review
from app.services.reviews import InterventionNotCompletedError, ensure_intervention_completed
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_service_request,
    make_trade,
    make_user,
)


def test_ensure_intervention_completed_rejects_non_terminee_status() -> None:
    intervention = Intervention(status=InterventionStatus.EN_COURS)

    with pytest.raises(InterventionNotCompletedError):
        ensure_intervention_completed(intervention)


def test_ensure_intervention_completed_accepts_terminee_status() -> None:
    intervention = Intervention(status=InterventionStatus.TERMINEE)

    ensure_intervention_completed(intervention)  # ne lève rien


async def test_db_trigger_rejects_review_on_non_completed_intervention(
    db_session: AsyncSession,
) -> None:
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
        status=InterventionStatus.EN_COURS,  # pas encore terminée
    )

    db_session.add(
        Review(
            intervention_id=intervention.id,
            author_id=client.id,
            artisan_id=artisan_profile.id,
            rating=5,
            comment="Trop tôt pour un avis.",
            contact_verified=True,
        )
    )
    with pytest.raises(DBAPIError, match="completed intervention"):
        await db_session.flush()


async def test_db_trigger_accepts_review_on_completed_intervention(
    db_session: AsyncSession,
) -> None:
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
        status=InterventionStatus.TERMINEE,
    )

    db_session.add(
        Review(
            intervention_id=intervention.id,
            author_id=client.id,
            artisan_id=artisan_profile.id,
            rating=5,
            comment="Intervention bien terminée.",
            contact_verified=True,
        )
    )
    await db_session.flush()  # ne doit pas lever
