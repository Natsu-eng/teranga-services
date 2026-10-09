"""Tests d'intégration du réencodage des photos de profil/couverture, du
point de vue HTTP : ce qui est réellement écrit et servi publiquement
(lot `feat/media-hardening`, app/services/image_processing.py)."""

from collections.abc import AsyncGenerator, Generator
from io import BytesIO
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.user import User
from app.services.rate_limit import SlidingWindowRateLimiter, get_profile_media_upload_rate_limiter
from tests.factories import make_artisan_profile, make_user
from tests.images import EXIF_GPS_IFD, make_jpeg, make_png, make_png_header_only


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession, tmp_path: Path) -> Generator[None, None, None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    settings = get_settings().model_copy(update={"avatar_storage_local_dir": str(tmp_path)})
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter
    yield
    for dependency in (get_session, get_settings, get_profile_media_upload_rate_limiter):
        app.dependency_overrides.pop(dependency, None)


async def _artisan(db_session: AsyncSession) -> User:
    user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=user)
    return user


async def _upload(user: User, kind: str, name: str, content: bytes, mime: str) -> dict[str, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/artisans/me/{kind}",
            headers={"Authorization": f"Bearer {encode_access_token(user)}"},
            files={"file": (name, content, mime)},
        )
    return {"status": response.status_code, "body": response.json()}


def _stored_image(tmp_path: Path, url: str) -> Image.Image:
    image = Image.open(tmp_path / url.rsplit("/static/avatars/", 1)[1])
    image.load()
    return image


@pytest.mark.parametrize("kind", ["avatar", "cover"])
async def test_gps_position_never_reaches_the_public_file(
    db_session: AsyncSession, tmp_path: Path, kind: str
) -> None:
    user = await _artisan(db_session)

    result = await _upload(
        user, kind, "photo.jpg", make_jpeg(800, 600, with_gps=True), "image/jpeg"
    )

    assert result["status"] == 200
    url = result["body"][f"{kind}_url"]  # type: ignore[index]
    stored = _stored_image(tmp_path, url)
    assert not stored.getexif().get_ifd(EXIF_GPS_IFD)
    assert b"TelephoneDeTest" not in (tmp_path / url.rsplit("/static/avatars/", 1)[1]).read_bytes()


async def test_each_media_is_resized_to_its_own_maximum(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user = await _artisan(db_session)
    settings = get_settings()
    big = make_jpeg(4000, 3000)

    avatar = await _upload(user, "avatar", "a.jpg", big, "image/jpeg")
    cover = await _upload(user, "cover", "c.jpg", big, "image/jpeg")

    avatar_image = _stored_image(tmp_path, avatar["body"]["avatar_url"])  # type: ignore[index]
    cover_image = _stored_image(tmp_path, cover["body"]["cover_url"])  # type: ignore[index]
    assert max(avatar_image.size) == settings.avatar_max_side_px
    assert max(cover_image.size) == settings.cover_max_side_px


async def test_decompression_bomb_is_refused_with_an_explicit_error(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user = await _artisan(db_session)

    result = await _upload(
        user, "cover", "bomb.png", make_png_header_only(8_000, 8_000), "image/png"
    )

    assert result["status"] == 422
    assert result["body"]["error"]["code"] == "IMAGE_DIMENSIONS_EXCESSIVES"  # type: ignore[index]
    assert list(tmp_path.rglob("*.*")) == []  # rien n'a été écrit


@pytest.mark.parametrize(
    ("kind", "code"), [("avatar", "AVATAR_TYPE_INVALIDE"), ("cover", "COUVERTURE_TYPE_INVALIDE")]
)
async def test_valid_signature_but_undecodable_content_is_refused(
    db_session: AsyncSession, tmp_path: Path, kind: str, code: str
) -> None:
    """Passe le contrôle des magic bytes (signature PNG valide) mais n'est
    pas une image : refusé au décodage, jamais écrit ni servi."""
    user = await _artisan(db_session)
    polyglot = b"\x89PNG\r\n\x1a\n" + b"<script>alert(1)</script>" * 4

    result = await _upload(user, kind, "x.png", polyglot, "image/png")

    assert result["status"] == 422
    assert result["body"]["error"]["code"] == code  # type: ignore[index]
    assert list(tmp_path.rglob("*.*")) == []


async def test_transparent_logo_keeps_its_transparency(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user = await _artisan(db_session)

    result = await _upload(user, "avatar", "logo.png", make_png(64, 64, alpha=True), "image/png")

    url = result["body"]["avatar_url"]  # type: ignore[index]
    assert url.endswith(".png")
    assert _stored_image(tmp_path, url).mode == "RGBA"


async def test_opaque_photo_is_stored_as_jpeg(db_session: AsyncSession, tmp_path: Path) -> None:
    user = await _artisan(db_session)

    result = await _upload(user, "avatar", "photo.png", make_png(64, 64), "image/png")

    url = result["body"]["avatar_url"]  # type: ignore[index]
    assert url.endswith(".jpg")
    assert (
        Image.open(BytesIO((tmp_path / url.rsplit("/static/avatars/", 1)[1]).read_bytes())).format
        == "JPEG"
    )
