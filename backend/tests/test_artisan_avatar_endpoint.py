"""Tests d'intégration de l'upload de photo de profil artisan (BUILD_PLAN.md,
onboarding artisan) : `POST /api/v1/artisans/me/avatar`.

Contrairement aux documents de vérification, un avatar est une donnée
PUBLIQUE -- ce test couvre surtout que le stockage/l'URL générée sont bien
distincts du stockage privé, et que la validation (magic bytes, taille,
rôle) suit les mêmes garde-fous.
"""

from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role
from app.services.rate_limit import SlidingWindowRateLimiter, get_profile_media_upload_rate_limiter
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png

_PNG_BYTES = make_png()
_FAKE_JPEG_BYTES = b"ceci n'est pas une image, juste renomme en .jpg"


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Une seule instance, réutilisée par le lambda (jamais reconstruite à
    # chaque résolution de dépendance FastAPI) -- sinon chaque requête
    # repartirait avec un compteur à zéro, désactivant la limite de fait.
    # Fraîche à chaque TEST : le singleton de production est un état
    # par-processus, partagé entre tests sinon (même raison que
    # test_ai_analyze_endpoint.py).
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path) -> Generator[None, None, None]:
    settings = get_settings().model_copy(update={"avatar_storage_local_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
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


async def test_nominal_avatar_upload_sets_a_public_absolute_url(
    db_session: AsyncSession,
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    settings = get_settings()

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 200
    avatar_url = response.json()["avatar_url"]
    assert avatar_url.startswith(f"{settings.backend_public_base_url}/static/avatars/")

    stmt = select(ArtisanProfile.avatar_url).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == avatar_url


async def test_falsified_extension_is_rejected_by_magic_bytes(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.jpg", _FAKE_JPEG_BYTES, "image/jpeg")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AVATAR_TYPE_INVALIDE"


async def test_oversized_avatar_is_rejected(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(
        update={"avatar_max_upload_bytes": 16}
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AVATAR_TROP_VOLUMINEUX"


async def test_client_role_cannot_upload_avatar(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    token = encode_access_token(client_user)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_unauthenticated_cannot_upload_avatar() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/avatar",
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 401


async def test_replacing_avatar_deletes_the_previous_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        first = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        first_url = first.json()["avatar_url"]
        first_key = first_url.rsplit("/static/avatars/", 1)[1]

        second_bytes = make_png(color=(17, 17, 17))
        second = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar2.png", second_bytes, "image/png")},
        )
        second_url = second.json()["avatar_url"]

    assert second_url != first_url
    assert not (tmp_path / first_key).exists()
