"""Tests d'intégration de la déclaration des métiers artisan (BUILD_PLAN.md,
onboarding artisan) : `POST/DELETE /api/v1/artisans/me/trades`.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.user import User
from tests.factories import make_artisan_profile, make_artisan_trade, make_trade, make_user


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


async def test_artisan_adds_a_trade(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="plomberie")

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 12_000,
                "service_radius_m": 8_000,
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 201
    body = response.json()
    assert len(body["trades"]) == 1
    assert body["trades"][0]["trade"]["code"] == trade.code
    assert body["trades"][0]["hourly_rate_fcfa"] == 12_000
    assert body["trades"][0]["has_custom_service_area"] is False


async def test_artisan_adds_trade_with_service_area_polygon(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="electricite")

    polygon = [
        {"lat": 14.70, "lng": -17.45},
        {"lat": 14.72, "lng": -17.45},
        {"lat": 14.72, "lng": -17.43},
        {"lat": 14.70, "lng": -17.45},  # ferme l'anneau
    ]

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 15_000,
                "service_radius_m": 5_000,
                "service_area": polygon,
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 201
    assert response.json()["trades"][0]["has_custom_service_area"] is True


async def test_unclosed_polygon_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="maconnerie")

    unclosed_polygon = [
        {"lat": 14.70, "lng": -17.45},
        {"lat": 14.72, "lng": -17.45},
        {"lat": 14.72, "lng": -17.43},
        {"lat": 14.71, "lng": -17.44},  # ne referme pas l'anneau
    ]

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 15_000,
                "service_radius_m": 5_000,
                "service_area": unclosed_polygon,
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ZONE_INTERVENTION_INVALIDE"


async def test_unknown_trade_code_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": "metier-qui-n-existe-pas",
                "hourly_rate_fcfa": 10_000,
                "service_radius_m": 5_000,
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "METIER_INTROUVABLE"


async def test_declaring_same_trade_twice_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="climatisation")
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 10_000,
                "service_radius_m": 5_000,
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ARTISAN_METIER_DEJA_DECLARE"


async def test_client_role_cannot_add_trade(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    trade = await make_trade(db_session, code="menuiserie")

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 10_000,
                "service_radius_m": 5_000,
            },
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_artisan_removes_own_trade(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="peinture")
    artisan_trade = await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.delete(
            f"/api/v1/artisans/me/trades/{artisan_trade.id}",
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200
    assert response.json()["trades"] == []


async def test_artisan_cannot_remove_another_artisans_trade(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN, full_name="Owner")
    owner_artisan = await make_artisan_profile(db_session, user=owner_user)
    trade = await make_trade(db_session, code="carrelage")
    owner_trade = await make_artisan_trade(db_session, artisan=owner_artisan, trade=trade)

    other_user = await make_user(db_session, role=Role.ARTISAN, full_name="Other")
    await make_artisan_profile(db_session, user=other_user)

    async with await _client() as client:
        response = await client.delete(
            f"/api/v1/artisans/me/trades/{owner_trade.id}",
            headers=_auth_headers(other_user),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTISAN_TRADE_NOT_FOUND"
