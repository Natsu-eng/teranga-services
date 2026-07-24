"""Test d'intégration de GET /api/v1/artisans/{id}/stats (BUILD_PLAN.md §5, §6 Lot 9).

Distinction publique/privée : les statistiques financières ne sont visibles
que par l'artisan lui-même ou un admin (dépendances de rôle du Lot 8).
"""

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import InterventionStatus, PaymentStatus, Role
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_payment,
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


async def _setup_artisan_with_revenue(
    db_session: AsyncSession,
) -> tuple[ArtisanProfile, User]:
    trade = await make_trade(db_session)
    owner_user = await make_user(db_session, role=Role.ARTISAN, full_name="Idrissa Test")
    artisan = await make_artisan_profile(db_session, user=owner_user)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    client = await make_user(db_session, role=Role.CLIENT)
    service_request = await make_service_request(db_session, client=client, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client,
        artisan=artisan,
        commission_rate=commission_rate,
        status=InterventionStatus.TERMINEE,
    )
    await make_payment(
        db_session, intervention=intervention, amount_fcfa=15_000, status=PaymentStatus.REUSSI
    )
    return artisan, owner_user


async def test_stats_anonymous_sees_only_reputation_indicators(db_session: AsyncSession) -> None:
    artisan, _ = await _setup_artisan_with_revenue(db_session)

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}/stats")

    assert response.status_code == 200
    body = response.json()
    assert "revenue_fcfa" not in body
    assert body["interventions_count"] == 1
    assert body["response_rate"] is None


async def test_stats_owner_sees_revenue(db_session: AsyncSession) -> None:
    artisan, owner_user = await _setup_artisan_with_revenue(db_session)
    token = encode_access_token(owner_user)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}/stats", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json()["revenue_fcfa"] == 15_000


async def test_stats_admin_sees_revenue(db_session: AsyncSession) -> None:
    artisan, _ = await _setup_artisan_with_revenue(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    token = encode_access_token(admin)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}/stats", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json()["revenue_fcfa"] == 15_000


async def test_stats_other_authenticated_user_gets_403(db_session: AsyncSession) -> None:
    artisan, _ = await _setup_artisan_with_revenue(db_session)
    other = await make_user(db_session, role=Role.CLIENT)
    token = encode_access_token(other)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}/stats", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STATISTIQUES_PRIVEES_INTERDITES"


async def test_stats_returns_normalized_404_for_unknown_artisan() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{uuid.uuid4()}/stats")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTISAN_NOT_FOUND"
