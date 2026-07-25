"""Test d'intégration de PATCH /api/v1/artisans/me (BUILD_PLAN.md §3.2).

Toggle de disponibilité, strictement limité à `is_available`, réservé au
rôle artisan et scopé à son propre `artisan_profile` (résolu depuis le
token, jamais reçu du client).
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role
from tests.factories import make_artisan_profile, make_user


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


async def test_client_role_cannot_toggle_availability(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    token = encode_access_token(client_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"is_available": False},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_unauthenticated_cannot_toggle_availability() -> None:
    async with await _client() as client:
        response = await client.patch("/api/v1/artisans/me", json={"is_available": False})

    assert response.status_code == 401


async def test_artisan_toggles_own_availability(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user, is_available=True)
    token = encode_access_token(owner_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"is_available": False},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["is_available"] is False

    stmt = select(ArtisanProfile.is_available).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted is False


async def test_artisan_cannot_modify_another_artisans_availability(
    db_session: AsyncSession,
) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN, full_name="Owner")
    owner_artisan = await make_artisan_profile(db_session, user=owner_user, is_available=True)
    other_user = await make_user(db_session, role=Role.ARTISAN, full_name="Other")
    other_artisan = await make_artisan_profile(db_session, user=other_user, is_available=True)
    other_token = encode_access_token(other_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"is_available": False},
            headers={"Authorization": f"Bearer {other_token}"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(other_artisan.id)

    stmt = select(ArtisanProfile.is_available).where(ArtisanProfile.id == owner_artisan.id)
    owner_still_available = (await db_session.execute(stmt)).scalar_one()
    assert owner_still_available is True
