"""Tests de fiabilité de la suppression des anciens médias de profil
(avatar/couverture, BUILD_PLAN.md lot `feat/profile-media`) -- voir les deux
règles du docstring de `app/services/profile_media.py`.

1. Un upload n'efface jamais que l'ancien fichier du MÊME artisan et du MÊME
   type de média, même si l'URL stockée a été remplacée à la main via
   `PATCH /artisans/me` par l'URL publique d'un autre fichier.
2. Le service ne supprime rien lui-même : l'effacement n'a lieu qu'après le
   commit, dans la route.

Plus la validation des URL saisies à la main (`avatar_url`/`cover_url`).
"""

import uuid
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
from app.models.user import User
from app.services import covers as covers_service
from app.services.profile_media import MediaKind, owned_media_key
from app.services.rate_limit import SlidingWindowRateLimiter, get_profile_media_upload_rate_limiter
from app.services.storage import LocalStorageBackend
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png

_PNG_BYTES = make_png()
_OTHER_PNG_BYTES = make_png(color=(34, 34, 34))


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Une seule instance par test (voir test_artisan_avatar_endpoint.py).
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path) -> Generator[None, None, None]:
    settings = get_settings().model_copy(update={"avatar_storage_local_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_profile_media_upload_rate_limiter, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


def _key_of(url: str) -> str:
    return url.rsplit("/static/avatars/", 1)[1]


async def test_cover_upload_never_deletes_another_artisans_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Attaque visée : l'attaquant colle dans SON `cover_url` l'URL publique
    de l'avatar de la victime, puis uploade une couverture -- le fichier de
    la victime doit survivre."""
    victim = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=victim)
    attacker = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=attacker)

    async with await _client() as client:
        victim_avatar = await client.post(
            "/api/v1/artisans/me/avatar",
            headers=_auth(victim),
            files={"file": ("a.png", _PNG_BYTES, "image/png")},
        )
        victim_url = victim_avatar.json()["avatar_url"]

        patched = await client.patch(
            "/api/v1/artisans/me", json={"cover_url": victim_url}, headers=_auth(attacker)
        )
        assert patched.status_code == 200

        upload = await client.post(
            "/api/v1/artisans/me/cover",
            headers=_auth(attacker),
            files={"file": ("c.png", _OTHER_PNG_BYTES, "image/png")},
        )

    assert upload.status_code == 200
    assert (tmp_path / _key_of(victim_url)).is_file()


async def test_avatar_upload_never_deletes_another_artisans_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    victim = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=victim)
    attacker = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=attacker)

    async with await _client() as client:
        victim_cover = await client.post(
            "/api/v1/artisans/me/cover",
            headers=_auth(victim),
            files={"file": ("c.png", _PNG_BYTES, "image/png")},
        )
        victim_url = victim_cover.json()["cover_url"]

        await client.patch(
            "/api/v1/artisans/me", json={"avatar_url": victim_url}, headers=_auth(attacker)
        )
        upload = await client.post(
            "/api/v1/artisans/me/avatar",
            headers=_auth(attacker),
            files={"file": ("a.png", _OTHER_PNG_BYTES, "image/png")},
        )

    assert upload.status_code == 200
    assert (tmp_path / _key_of(victim_url)).is_file()


async def test_cover_upload_never_deletes_own_avatar_pasted_as_cover(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Même artisan, autre type de média : réutiliser l'URL de son avatar
    comme couverture puis uploader une vraie couverture ne doit pas effacer
    l'avatar (toujours affiché, lui)."""
    owner = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner)

    async with await _client() as client:
        avatar = await client.post(
            "/api/v1/artisans/me/avatar",
            headers=_auth(owner),
            files={"file": ("a.png", _PNG_BYTES, "image/png")},
        )
        avatar_url = avatar.json()["avatar_url"]
        await client.patch(
            "/api/v1/artisans/me", json={"cover_url": avatar_url}, headers=_auth(owner)
        )
        await client.post(
            "/api/v1/artisans/me/cover",
            headers=_auth(owner),
            files={"file": ("c.png", _OTHER_PNG_BYTES, "image/png")},
        )

    assert (tmp_path / _key_of(avatar_url)).is_file()


async def test_service_leaves_the_previous_file_until_the_route_has_committed(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Règle 2 : appelé seul (sans la route, donc sans commit), le service
    ne touche pas à l'ancien fichier -- il se contente de désigner sa clé."""
    owner = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner)
    settings = app.dependency_overrides[get_settings]()
    storage = LocalStorageBackend(tmp_path)

    first = await covers_service.upload_cover(
        db_session, user=owner, content=_PNG_BYTES, settings=settings, storage=storage
    )
    assert first.obsolete_key is None
    first_key = _key_of(first.detail.cover_url or "")

    second = await covers_service.upload_cover(
        db_session, user=owner, content=_OTHER_PNG_BYTES, settings=settings, storage=storage
    )

    assert second.obsolete_key == first_key
    assert (tmp_path / first_key).is_file()


def test_owned_media_key_only_accepts_the_exact_generated_format() -> None:
    settings = get_settings()
    base = f"{settings.backend_public_base_url}/static/avatars"
    profile_id = uuid.uuid4()
    other_id = uuid.uuid4()
    hex_ = "a" * 32

    def key(url: str, kind: MediaKind) -> str | None:
        return owned_media_key(url, settings=settings, profile_id=profile_id, kind=kind)

    assert key(f"{base}/{profile_id}/cover-{hex_}.png", MediaKind.COVER) == (
        f"{profile_id}/cover-{hex_}.png"
    )
    assert key(f"{base}/{profile_id}/{hex_}.jpg", MediaKind.AVATAR) == f"{profile_id}/{hex_}.jpg"
    # Autre artisan, autre type, traversée, extension inattendue, URL externe.
    assert key(f"{base}/{other_id}/cover-{hex_}.png", MediaKind.COVER) is None
    assert key(f"{base}/{profile_id}/{hex_}.png", MediaKind.COVER) is None
    assert key(f"{base}/{profile_id}/cover-{hex_}.png", MediaKind.AVATAR) is None
    assert key(f"{base}/{profile_id}/../{other_id}/{hex_}.png", MediaKind.AVATAR) is None
    assert key(f"{base}/{profile_id}/{hex_}.pdf", MediaKind.AVATAR) is None
    assert key(f"https://cdn.example.invalid/{profile_id}/{hex_}.png", MediaKind.AVATAR) is None


@pytest.mark.parametrize(
    "bad_url", ["javascript:alert(1)", "data:image/png;base64,AAAA", "/images/x.png", "ftp://x/y"]
)
async def test_patch_rejects_non_http_media_urls(db_session: AsyncSession, bad_url: str) -> None:
    owner = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=owner)

    async with await _client() as client:
        for field in ("avatar_url", "cover_url"):
            response = await client.patch(
                "/api/v1/artisans/me", json={field: bad_url}, headers=_auth(owner)
            )
            assert response.status_code == 422, field


async def test_patch_accepts_https_cover_and_blank_clears_it(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, role=Role.ARTISAN)
    profile = await make_artisan_profile(db_session, user=owner)
    url = "https://cdn.example.invalid/covers/atelier.jpg"

    async with await _client() as client:
        set_response = await client.patch(
            "/api/v1/artisans/me", json={"cover_url": f"  {url}  "}, headers=_auth(owner)
        )
        assert set_response.status_code == 200
        assert set_response.json()["cover_url"] == url

        clear_response = await client.patch(
            "/api/v1/artisans/me", json={"cover_url": "   "}, headers=_auth(owner)
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["cover_url"] is None

    stmt = select(ArtisanProfile.cover_url).where(ArtisanProfile.id == profile.id)
    assert (await db_session.execute(stmt)).scalar_one() is None
