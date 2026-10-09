"""`GET /api/v1/artisans/me/media-constraints` : seule source de vérité des
limites d'envoi des photos de profil, lue par le front (lot
`feat/media-hardening`) -- elle doit refléter EXACTEMENT ce que les routes
d'upload appliquent."""

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
from tests.images import make_jpeg

_URL = "/api/v1/artisans/me/media-constraints"


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession, tmp_path: Path) -> Generator[None, None, None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter
    yield
    for dependency in (get_session, get_settings, get_profile_media_upload_rate_limiter):
        app.dependency_overrides.pop(dependency, None)


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_returns_the_limits_the_server_actually_applies(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=user)
    settings = get_settings()

    async with await _client() as client:
        response = await client.get(
            _URL, headers={"Authorization": f"Bearer {encode_access_token(user)}"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "accepted_mime_types": ["image/jpeg", "image/png"],
        "max_pixels": settings.profile_media_max_pixels,
        "avatar": {
            "max_upload_bytes": settings.avatar_max_upload_bytes,
            "max_side_px": settings.avatar_max_side_px,
        },
        "cover": {
            "max_upload_bytes": settings.cover_max_upload_bytes,
            "max_side_px": settings.cover_max_side_px,
        },
    }


async def test_announced_limit_is_the_enforced_limit(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Un réglage modifié change À LA FOIS ce qui est annoncé et ce qui est
    appliqué : un fichier d'un octet de plus que l'annonce est refusé."""
    user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=user)
    photo = make_jpeg(64, 64)
    settings = get_settings().model_copy(
        update={"cover_max_upload_bytes": len(photo) - 1, "avatar_storage_local_dir": str(tmp_path)}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    headers = {"Authorization": f"Bearer {encode_access_token(user)}"}

    async with await _client() as client:
        announced = (await client.get(_URL, headers=headers)).json()["cover"]["max_upload_bytes"]
        upload = await client.post(
            "/api/v1/artisans/me/cover",
            headers=headers,
            files={"file": ("c.jpg", photo, "image/jpeg")},
        )

    assert announced == len(photo) - 1
    assert upload.status_code == 413


async def test_client_role_is_refused(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as client:
        response = await client.get(
            _URL, headers={"Authorization": f"Bearer {encode_access_token(client_user)}"}
        )

    assert response.status_code == 403


async def test_anonymous_is_refused() -> None:
    async with await _client() as client:
        response = await client.get(_URL)

    assert response.status_code == 401
