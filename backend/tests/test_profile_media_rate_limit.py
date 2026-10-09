"""Rate limiting de `POST /api/v1/artisans/me/avatar` et `.../me/cover`
(BUILD_PLAN.md, lot `feat/profile-media`) : budget partagé entre les deux
endpoints, même limiteur, même clé par utilisateur authentifié.
"""

from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.services.rate_limit import SlidingWindowRateLimiter, get_profile_media_upload_rate_limiter
from tests.factories import make_artisan_profile, make_user

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _isolate_storage_and_limit(tmp_path: Path) -> Generator[None, None, None]:
    # Plafond bas (2) pour déclencher la limite en quelques appels, sans
    # dépendre du défaut de production (20) dans le test.
    settings = get_settings().model_copy(
        update={
            "avatar_storage_local_dir": str(tmp_path),
            "rate_limit_profile_media_upload_per_user_max": 2,
        }
    )
    # Une seule instance, réutilisée par le lambda -- sinon chaque requête
    # repartirait avec un compteur à zéro (le lambda serait rappelé à
    # chaque résolution de dépendance FastAPI), désactivant la limite de
    # fait au lieu de la tester.
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter
    yield


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_profile_media_upload_rate_limiter, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_avatar_and_cover_share_the_same_rate_limit_budget(db_session: AsyncSession) -> None:
    """Plafond à 2 : 1 avatar + 1 cover consomment déjà tout le budget --
    un 3e appel, peu importe lequel des deux endpoints, est rejeté."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        first = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        second = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )
        third = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar2.png", _PNG_BYTES, "image/png")},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "TROP_DE_DEMANDES"


async def test_rate_limit_is_scoped_per_user(db_session: AsyncSession) -> None:
    """Un artisan qui a épuisé son budget ne doit jamais bloquer un autre --
    la clé du limiteur est `user:{id}`, pas globale."""
    exhausted_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=exhausted_user)
    exhausted_token = encode_access_token(exhausted_user)

    fresh_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=fresh_user)
    fresh_token = encode_access_token(fresh_user)

    async with await _client() as client:
        await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {exhausted_token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {exhausted_token}"},
            files={"file": ("avatar2.png", _PNG_BYTES, "image/png")},
        )
        blocked = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {exhausted_token}"},
            files={"file": ("avatar3.png", _PNG_BYTES, "image/png")},
        )
        still_allowed = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {fresh_token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )

    assert blocked.status_code == 429
    assert still_allowed.status_code == 200
