"""Tests d'intégration de l'édition du profil artisan (BUILD_PLAN.md,
onboarding artisan) : `PATCH /api/v1/artisans/me` étendu au-delà du seul
`is_available` (bio, années d'expérience, localisation, avatar).
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
from app.models.enums import ArtisanVerifiedStatus, Role
from app.models.user import User
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


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def test_artisan_edits_bio_experience_avatar(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user, bio=None)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={
                "bio": "Plombier sérieux, 10 ans d'expérience à Dakar.",
                "years_experience": 10,
                "avatar_url": "https://cdn.example.invalid/avatars/idrissa.jpg",
            },
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["bio"] == "Plombier sérieux, 10 ans d'expérience à Dakar."
    assert body["years_experience"] == 10

    stmt = select(ArtisanProfile).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted.bio == "Plombier sérieux, 10 ans d'expérience à Dakar."
    assert persisted.avatar_url == "https://cdn.example.invalid/avatars/idrissa.jpg"


async def test_partial_update_leaves_other_fields_untouched(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user, bio="Bio initiale.")
    artisan.years_experience = 5
    await db_session.flush()

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"years_experience": 7},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200
    assert response.json()["bio"] == "Bio initiale."
    assert response.json()["years_experience"] == 7


async def test_is_available_only_still_works_unchanged(db_session: AsyncSession) -> None:
    """Non-régression : le toggle historique (Lot 12c) continue de
    fonctionner à l'identique sur ce même endpoint désormais étendu."""
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user, is_available=True)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"is_available": False},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200
    assert response.json()["is_available"] is False


async def test_updates_base_location(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"base_location": {"lat": 14.7167, "lng": -17.4677}},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200


async def test_invalid_base_location_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"base_location": {"lat": 200, "lng": -17.4677}},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 422


async def test_years_experience_out_of_bounds_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"years_experience": -1},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 422


async def test_bio_too_long_is_rejected(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner_user)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"bio": "x" * 2001},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 422


async def test_cannot_set_verified_status_via_profile_update(db_session: AsyncSession) -> None:
    """`verified_status` n'apparaît pas dans le schéma d'entrée -- un champ
    inconnu est simplement ignoré par Pydantic, jamais appliqué."""
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user)
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await db_session.flush()

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/artisans/me",
            json={"verified_status": "verified", "bio": "Test."},
            headers=_auth_headers(owner_user),
        )

    assert response.status_code == 200
    stmt = select(ArtisanProfile.verified_status).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == ArtisanVerifiedStatus.NONE  # jamais modifié via ce endpoint
