"""Devis (BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b) : total calculé serveur,
un seul devis actif par intervention (remplacement, pas empilement),
isolation des rôles.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import InterventionStatus, Role
from app.models.intervention import Quote
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_quote,
    make_service_request,
    make_trade,
    make_user,
)


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def test_artisan_creates_quote_with_server_computed_total(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote",
            # Un total explicite, différent de labor+materials, ne doit
            # jamais être pris en compte -- il n'est même pas dans le schéma
            # d'entrée (QuoteCreateIn n'a pas de champ `total_fcfa`).
            json={"labor_fcfa": 15_000, "materials_fcfa": 5_000},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quote"]["labor_fcfa"] == 15_000
    assert body["quote"]["materials_fcfa"] == 5_000
    assert body["quote"]["total_fcfa"] == 20_000
    assert body["quote"]["status"] == "propose"
    assert body["status"] == "acceptee"  # inchangé : un devis ne transitionne pas seul


async def test_create_quote_rejects_non_accepted_intervention(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.PROPOSEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote",
            json={"labor_fcfa": 8_000, "materials_fcfa": 4_000},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "QUOTE_INTERVENTION_NON_ACCEPTEE"


async def test_create_quote_rejects_an_unrelated_artisan(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )
    unrelated_artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=unrelated_artisan_user)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote",
            json={"labor_fcfa": 8_000, "materials_fcfa": 4_000},
            headers=_auth_headers(unrelated_artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_RESERVEE_AUTRE_PARTIE"


async def test_re_quoting_replaces_the_previous_quote_instead_of_stacking(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )
    first_quote = await make_quote(
        db_session, intervention=intervention, labor_fcfa=8_000, materials_fcfa=4_000
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote",
            json={"labor_fcfa": 20_000, "materials_fcfa": 10_000},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quote"]["total_fcfa"] == 30_000
    assert body["quote"]["id"] != str(first_quote.id)

    count = (
        await db_session.execute(
            select(func.count()).select_from(Quote).where(Quote.intervention_id == intervention.id)
        )
    ).scalar_one()
    assert count == 1


async def test_client_accepts_quote_moves_intervention_to_en_cours(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )
    await make_quote(db_session, intervention=intervention, labor_fcfa=15_000, materials_fcfa=5_000)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote/accept",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "en_cours"
    assert body["agreed_amount_fcfa"] == 20_000
    assert body["quote"]["status"] == "accepte"


async def test_accept_quote_rejects_when_no_active_quote(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote/accept",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUCUN_DEVIS_ACTIF"


async def test_accept_quote_rejects_an_unrelated_client(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    stranger = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )
    await make_quote(db_session, intervention=intervention)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote/accept", headers=_auth_headers(stranger)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_RESERVEE_AUTRE_PARTIE"


async def test_client_refuses_quote_keeps_intervention_accepted(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )
    await make_quote(db_session, intervention=intervention)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote/refuse",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acceptee"
    assert body["quote"]["status"] == "refuse"
    assert body["agreed_amount_fcfa"] is None


async def test_refuse_quote_rejects_when_no_active_quote(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/quote/refuse",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUCUN_DEVIS_ACTIF"
