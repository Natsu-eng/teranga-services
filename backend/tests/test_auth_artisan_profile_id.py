"""`GET /auth/me` expose `artisan_profile_id` (AUDIT_PHASE2.md §6, BUILD_PLAN.md
§6 Lot 12) : ferme le lien `user <-> artisan_profile` sur lequel le front
s'appuyait jusqu'ici via un placeholder (`artisanId = user.id`).
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


async def test_me_exposes_null_artisan_profile_id_for_a_client(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        response = await http.get("/api/v1/auth/me", headers=_auth_headers(client_user))

    assert response.status_code == 200
    assert response.json()["artisan_profile_id"] is None


async def test_me_exposes_the_real_artisan_profile_id_for_an_artisan(
    db_session: AsyncSession,
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan_profile = await make_artisan_profile(db_session, user=artisan_user)

    async with await _client() as http:
        response = await http.get("/api/v1/auth/me", headers=_auth_headers(artisan_user))

    assert response.status_code == 200
    body = response.json()
    assert body["artisan_profile_id"] == str(artisan_profile.id)
    # La distinction qui compte : ce n'est PAS l'id du user (l'ancien
    # placeholder front `artisanId = user.id`) mais bien celui du profil.
    assert body["artisan_profile_id"] != body["id"]


async def test_me_exposes_null_artisan_profile_id_for_artisan_role_without_profile(
    db_session: AsyncSession,
) -> None:
    # Cas limite : rôle `artisan` mais aucun `artisan_profile` créé --
    # ne doit jamais planter, `None` est la réponse honnête.
    artisan_user = await make_user(db_session, role=Role.ARTISAN)

    async with await _client() as http:
        response = await http.get("/api/v1/auth/me", headers=_auth_headers(artisan_user))

    assert response.status_code == 200
    assert response.json()["artisan_profile_id"] is None
