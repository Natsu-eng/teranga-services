"""Tests d'intégration de l'upload de photo de couverture artisan
(BUILD_PLAN.md, lot `feat/profile-media`) : `POST /api/v1/artisans/me/cover`.

Miroir de `test_artisan_avatar_endpoint.py` (même régime PUBLIC, même
stockage, mêmes garde-fous) -- ajoute les cas propres à ce lot : isolation
entre artisans (task 4, "un artisan ne modifie que SON média") et rate
limiting (partagé avec l'avatar, voir `test_profile_media_rate_limit.py`).
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

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_FAKE_JPEG_BYTES = b"ceci n'est pas une image, juste renomme en .jpg"


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Une seule instance, réutilisée par le lambda (voir
    # test_artisan_avatar_endpoint.py pour le raisonnement complet).
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


async def test_nominal_cover_upload_sets_a_public_absolute_url(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    settings = get_settings()

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 200
    cover_url = response.json()["cover_url"]
    assert cover_url.startswith(f"{settings.backend_public_base_url}/static/avatars/")
    assert "/cover-" in cover_url

    stmt = select(ArtisanProfile.cover_url).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == cover_url


async def test_falsified_extension_is_rejected_by_magic_bytes(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.jpg", _FAKE_JPEG_BYTES, "image/jpeg")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COUVERTURE_TYPE_INVALIDE"


async def test_oversized_cover_is_rejected(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(
        update={"cover_max_upload_bytes": 16}
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "COUVERTURE_TROP_VOLUMINEUSE"


async def test_client_role_cannot_upload_cover(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    token = encode_access_token(client_user)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_unauthenticated_cannot_upload_cover() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/cover",
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 401


async def test_replacing_cover_deletes_the_previous_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        first = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )
        first_url = first.json()["cover_url"]
        first_key = first_url.rsplit("/static/avatars/", 1)[1]

        second_bytes = b"\x89PNG\r\n\x1a\n" + b"\x11" * 32
        second = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover2.png", second_bytes, "image/png")},
        )
        second_url = second.json()["cover_url"]

    assert second_url != first_url
    assert not (tmp_path / first_key).exists()


async def test_uploading_a_cover_never_touches_the_avatar(db_session: AsyncSession) -> None:
    """L'avatar et la couverture vivent sur deux colonnes distinctes --
    uploader l'un ne doit jamais écraser ni effacer l'autre."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        avatar_response = await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        avatar_url = avatar_response.json()["avatar_url"]

        cover_response = await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    assert cover_response.json()["avatar_url"] == avatar_url

    stmt = select(ArtisanProfile.avatar_url, ArtisanProfile.cover_url).where(
        ArtisanProfile.id == artisan.id
    )
    persisted_avatar, persisted_cover = (await db_session.execute(stmt)).one()
    assert persisted_avatar == avatar_url
    assert persisted_cover == cover_response.json()["cover_url"]
    assert persisted_avatar != persisted_cover


async def test_an_artisan_only_ever_modifies_their_own_media(db_session: AsyncSession) -> None:
    """Task 4 : « un artisan ne modifie que SON média » -- l'upload est
    toujours résolu depuis le token (`get_own_profile`), jamais depuis un id
    reçu du client (il n'y en a d'ailleurs aucun dans cette route)."""
    owner = await make_user(db_session, role=Role.ARTISAN)
    owner_profile = await make_artisan_profile(db_session, user=owner)
    other = await make_user(db_session, role=Role.ARTISAN)
    other_profile = await make_artisan_profile(db_session, user=other)
    owner_token = encode_access_token(owner)

    async with await _client() as client:
        await client.post(
            "/api/v1/artisans/me/avatar",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        await client.post(
            "/api/v1/artisans/me/cover",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("cover.png", _PNG_BYTES, "image/png")},
        )

    stmt = select(ArtisanProfile.avatar_url, ArtisanProfile.cover_url).where(
        ArtisanProfile.id == other_profile.id
    )
    other_avatar, other_cover = (await db_session.execute(stmt)).one()
    assert other_avatar is None
    assert other_cover is None

    stmt = select(ArtisanProfile.avatar_url, ArtisanProfile.cover_url).where(
        ArtisanProfile.id == owner_profile.id
    )
    owner_avatar, owner_cover = (await db_session.execute(stmt)).one()
    assert owner_avatar is not None
    assert owner_cover is not None
