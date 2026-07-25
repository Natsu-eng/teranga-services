"""Dépôt d'un avis (BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b) : verrouillé côté
service (erreur normalisée) ET côté trigger DB (filet de sécurité, déjà
couvert par `test_business_rules.py`), un seul avis par intervention,
recalcul de `rating_avg`/`review_count` de l'artisan.
"""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import InterventionStatus, Role
from app.models.review import Review
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_review,
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


async def test_client_reviews_a_completed_intervention_and_recalculates_rating(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    client_user.phone_verified_at = datetime.now(UTC)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.TERMINEE,
    )
    await db_session.flush()

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 5, "comment": "Travail impeccable, très professionnel."},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 5
    assert body["author_name"] == client_user.full_name

    await db_session.refresh(artisan)
    assert artisan.rating_avg == Decimal("5.00")
    assert artisan.review_count == 1


async def test_contact_verified_reflects_the_authors_phone_verification(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    # Pas de phone_verified_at posé -- compte jamais passé par l'OTP.
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.TERMINEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 4, "comment": "Bon travail."},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 201
    stored = await db_session.get(Review, response.json()["id"])
    assert stored is not None
    assert stored.contact_verified is False


async def test_create_review_rejects_a_non_completed_intervention(
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
        status=InterventionStatus.EN_COURS,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 5, "comment": "Trop tôt."},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AVIS_INTERVENTION_NON_TERMINEE"


async def test_create_review_rejects_a_second_review_on_the_same_intervention(
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
        status=InterventionStatus.TERMINEE,
    )
    await make_review(db_session, intervention=intervention, author=client_user, artisan=artisan)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 3, "comment": "Deuxième tentative."},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AVIS_DEJA_DEPOSE"


async def test_create_review_rejects_an_unrelated_client(db_session: AsyncSession) -> None:
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
        status=InterventionStatus.TERMINEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 5, "comment": "Pas mon intervention."},
            headers=_auth_headers(stranger),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_RESERVEE_AUTRE_PARTIE"


async def test_create_review_rejects_artisan_role(db_session: AsyncSession) -> None:
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
        status=InterventionStatus.TERMINEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 5, "comment": "Auto-avis."},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_new_review_appears_in_the_public_reviews_list(db_session: AsyncSession) -> None:
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
        status=InterventionStatus.TERMINEE,
    )

    async with await _client() as http:
        create_response = await http.post(
            f"/api/v1/interventions/{intervention.id}/review",
            json={"rating": 5, "comment": "Visible publiquement."},
            headers=_auth_headers(client_user),
        )
        assert create_response.status_code == 201

        list_response = await http.get(f"/api/v1/artisans/{artisan.id}/reviews")

    comments = [item["comment"] for item in list_response.json()["items"]]
    assert "Visible publiquement." in comments
