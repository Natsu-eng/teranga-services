"""Vue d'ensemble du back-office : chaque chiffre suit les données réelles.

La base de dev contient déjà des données : on mesure donc des ÉCARTS
avant/après création de données connues, dans la transaction du test.
"""

from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import (
    ArtisanVerifiedStatus,
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
    Role,
    VerificationStatus,
)
from app.models.intervention import InterventionDispute
from app.models.payment import PlatformFee
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_engagement,
    make_payment,
    make_user,
    make_verification,
)


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Iterator[None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.pop(get_session, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, int]:
    flat: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        elif isinstance(value, int):
            flat[f"{prefix}{key}"] = value
    return flat


async def _overview(admin: User) -> dict[str, int]:
    async with _client() as http:
        response = await http.get("/api/v1/admin/overview", headers=_auth(admin))
    assert response.status_code == 200, response.text
    return _flatten(response.json())


async def test_every_figure_is_a_non_negative_integer(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)

    figures = await _overview(admin)

    assert figures, "la vue d'ensemble doit exposer des chiffres"
    assert all(value >= 0 for value in figures.values())
    for key in (
        "artisans.total",
        "users.clients",
        "interventions.en_cours",
        "money.business_volume_fcfa",
        "money.commission_due_fcfa",
        "pending_verifications",
        "open_disputes",
    ):
        assert key in figures


async def test_figures_follow_the_real_data(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    before = await _overview(admin)

    # Un client, un artisan en attente avec un document à examiner.
    await make_user(db_session, role=Role.CLIENT)
    pending_artisan = await make_artisan_profile(db_session)
    pending_artisan.verified_status = ArtisanVerifiedStatus.PENDING
    await make_verification(db_session, artisan=pending_artisan, status=VerificationStatus.PENDING)
    # Une intervention payée en ligne (séquestre), une terminée réglée en
    # espèces avec sa commission due, une en litige ouvert.
    escrow = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    await make_payment(
        db_session,
        intervention=escrow.intervention,
        amount_fcfa=12_000,
        status=PaymentStatus.RETENU,
    )
    cash = await make_engagement(db_session, status=InterventionStatus.TERMINEE)
    await make_payment(
        db_session,
        intervention=cash.intervention,
        amount_fcfa=20_000,
        status=PaymentStatus.REUSSI,
        channel=PaymentChannel.CASH,
    )
    db_session.add(
        PlatformFee(
            intervention_id=cash.intervention.id,
            kind=PlatformFeeKind.COMMISSION,
            amount_fcfa=2_000,
            commission_rate_id=cash.intervention.commission_rate_id,
            status=PlatformFeeStatus.DUE,
        )
    )
    disputed = await make_engagement(db_session, status=InterventionStatus.LITIGE)
    db_session.add(
        InterventionDispute(
            intervention_id=disputed.intervention.id,
            opened_by_id=disputed.client.id,
            opened_by_role=Role.CLIENT,
            reason="Travaux non terminés.",
        )
    )
    await db_session.flush()

    after = await _overview(admin)
    delta = {key: after[key] - before[key] for key in before}

    # make_engagement crée aussi un client et un artisan par intervention ;
    # make_artisan_profile, le compte de l'artisan en attente.
    assert delta["users.clients"] == 1 + 3
    assert delta["users.artisans"] == 1 + 3
    assert delta["artisans.pending"] == 1
    assert delta["pending_verifications"] == 1
    assert delta["interventions.en_cours"] == 1
    assert delta["interventions.terminee"] == 1
    assert delta["interventions.litige"] == 1
    assert delta["open_disputes"] == 1
    assert delta["money.in_escrow_fcfa"] == 12_000
    assert delta["money.cash_fcfa"] == 20_000
    assert delta["money.business_volume_fcfa"] == 32_000
    assert delta["money.commission_due_fcfa"] == 2_000
    assert delta["money.commission_collected_fcfa"] == 0


async def test_the_overview_is_reserved_to_admins(db_session: AsyncSession) -> None:
    client = await make_user(db_session, role=Role.CLIENT)

    async with _client() as http:
        anonymous = await http.get("/api/v1/admin/overview")
        as_client = await http.get("/api/v1/admin/overview", headers=_auth(client))

    assert anonymous.status_code == 401
    assert as_client.status_code == 403
