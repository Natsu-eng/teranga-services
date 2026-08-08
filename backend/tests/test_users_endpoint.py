"""Tests d'intégration de `PATCH /api/v1/users/me` (BUILD_PLAN.md, fix
confidentialité du contact) : édition du nom, rôle-agnostique (client ET
artisan), toujours scopée au compte authentifié.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.user import User
from tests.factories import make_user


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


async def test_client_edits_own_full_name(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT, full_name="Nom Provisoire")

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "Diandé Diallo"},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Diandé Diallo"

    stmt = select(User.full_name).where(User.id == user.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == "Diandé Diallo"


async def test_artisan_can_also_use_this_endpoint(db_session: AsyncSession) -> None:
    """Rôle-agnostique par construction -- pas de `require_role`, seule
    l'authentification est exigée."""
    user = await make_user(db_session, role=Role.ARTISAN)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "Idrissa Diop"},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Idrissa Diop"


async def test_full_name_is_trimmed(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "  Diandé Diallo  "},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Diandé Diallo"


async def test_blank_full_name_is_rejected(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT, full_name="Nom Initial")

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "   "},
            headers=_auth_headers(user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOM_INVALIDE"

    stmt = select(User.full_name).where(User.id == user.id)
    unchanged = (await db_session.execute(stmt)).scalar_one()
    assert unchanged == "Nom Initial"


async def test_missing_full_name_is_rejected(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={},
            headers=_auth_headers(user),
        )

    assert response.status_code == 422


async def test_unauthenticated_cannot_edit_a_name() -> None:
    async with await _client() as client:
        response = await client.patch("/api/v1/users/me", json={"full_name": "Quelqu'un"})

    assert response.status_code == 401


async def test_cannot_edit_another_users_name(db_session: AsyncSession) -> None:
    """Aucun id de cible dans la requête -- structurellement impossible de
    viser un autre compte, seul celui résolu depuis le token est édité."""
    owner = await make_user(db_session, role=Role.CLIENT, full_name="Owner")
    other = await make_user(db_session, role=Role.CLIENT, full_name="Other")

    async with await _client() as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "Usurpateur"},
            headers=_auth_headers(other),
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Usurpateur"

    stmt = select(User.full_name).where(User.id == owner.id)
    owner_untouched = (await db_session.execute(stmt)).scalar_one()
    assert owner_untouched == "Owner"
