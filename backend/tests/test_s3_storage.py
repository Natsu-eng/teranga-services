"""Stockage S3-compatible (app/services/s3_storage.py) et séparation privé/public.

Aucun réseau : `FakeS3` imite le sous-ensemble de boto3 utilisé et garde,
pour chaque objet, son bucket, sa clé et ses en-têtes -- de quoi PROUVER
qu'un document d'identité n'atterrit jamais dans le bucket public.
"""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.services import storage
from app.services.rate_limit import (
    SlidingWindowRateLimiter,
    get_document_upload_rate_limiter,
    get_profile_media_upload_rate_limiter,
)
from app.services.s3_storage import (
    PRIVATE_CACHE_CONTROL,
    PUBLIC_CACHE_CONTROL,
    S3StorageBackend,
)
from app.services.storage import (
    LocalStorageBackend,
    StorageObjectIntrouvableError,
    get_avatar_storage_backend,
    get_message_attachment_storage_backend,
    get_storage_backend,
)
from tests.deployed_settings import DEPLOYED_REQUIRED
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png

PRIVATE = "teranga-prive"
PUBLIC = "teranga-public"
PUBLIC_URL = "https://media.teranga.sn"

S3_SETTINGS: dict[str, object] = {
    "storage_backend": "s3",
    "s3_endpoint_url": "https://compte.r2.cloudflarestorage.com",
    "s3_access_key_id": "cle-de-test",
    "s3_secret_access_key": "secret-de-test-0123456789",
    "s3_private_bucket": PRIVATE,
    "s3_public_bucket": PUBLIC,
    "s3_public_base_url": PUBLIC_URL,
}


@dataclass
class StoredObject:
    body: bytes
    content_type: str
    cache_control: str
    acl: str | None


class FakeS3:
    """Buckets en mémoire ; chaque appel est consigné."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, StoredObject]] = {PRIVATE: {}, PUBLIC: {}}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.buckets[kwargs["Bucket"]][kwargs["Key"]] = StoredObject(
            body=kwargs["Body"],
            content_type=kwargs["ContentType"],
            cache_control=kwargs["CacheControl"],
            acl=kwargs.get("ACL"),
        )
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        stored = self.buckets[kwargs["Bucket"]].get(kwargs["Key"])
        if stored is None:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": BytesIO(stored.body)}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.buckets[kwargs["Bucket"]].pop(kwargs["Key"], None)
        return {}


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        **DEPLOYED_REQUIRED,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr(storage, "get_s3_client", lambda _settings: fake)
    return fake


# ----------------------------------------------------------------- réglages


def test_local_storage_stays_the_default_everywhere() -> None:
    settings = _settings()
    assert (
        settings.storage_backend,
        settings.avatar_storage_backend,
        settings.message_attachment_storage_backend,
    ) == ("local", "local", "local")
    assert isinstance(get_storage_backend(settings), LocalStorageBackend)
    assert isinstance(get_avatar_storage_backend(settings), LocalStorageBackend)


def test_storage_backend_s3_switches_every_store(fake_s3: FakeS3) -> None:
    settings = _settings(**S3_SETTINGS)
    assert settings.avatar_storage_backend == "s3"
    assert settings.message_attachment_storage_backend == "s3"
    for factory in (
        get_storage_backend,
        get_avatar_storage_backend,
        get_message_attachment_storage_backend,
    ):
        assert isinstance(factory(settings), S3StorageBackend)


def test_incomplete_s3_configuration_names_what_is_missing() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(storage_backend="s3")
    message = str(exc.value)
    for name in (
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "S3_PRIVATE_BUCKET",
        "S3_PUBLIC_BUCKET",
        "S3_PUBLIC_BASE_URL",
    ):
        assert name in message


def test_private_and_public_buckets_must_differ() -> None:
    with pytest.raises(ValidationError, match="deux buckets différents"):
        _settings(**{**S3_SETTINGS, "s3_public_bucket": PRIVATE})


def test_production_refuses_local_storage() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(
            environment="production",
            database_url="postgresql+asyncpg://teranga:S9vR2kLq7ZtW4mPx@db.internal:5432/teranga",
            jwt_secret="Q2x9mV7pLr4tZb8NwK3sHc6YdF1gJ5uEaT0oRiXy",
            frontend_public_base_url="https://teranga.sn",
            backend_public_base_url="https://api.teranga.sn",
        )
    message = str(exc.value)
    assert "STORAGE_BACKEND=local est interdit en production" in message
    assert "AVATAR_STORAGE_BACKEND=local" in message
    assert "MESSAGE_ATTACHMENT_STORAGE_BACKEND=local" in message


# ------------------------------------------------------------ backend S3


async def test_private_objects_are_never_cacheable_nor_public(fake_s3: FakeS3) -> None:
    settings = _settings(**S3_SETTINGS)
    document = get_storage_backend(settings)

    reference = await document.store(b"cni", "artisan-1/cni.png")

    stored = fake_s3.buckets[PRIVATE]["verification-documents/artisan-1/cni.png"]
    assert reference == "artisan-1/cni.png"  # référence opaque, sans bucket
    assert stored.cache_control == PRIVATE_CACHE_CONTROL
    assert stored.acl is None  # jamais d'ACL publique, objet par objet
    assert stored.content_type == "image/png"
    assert fake_s3.buckets[PUBLIC] == {}
    assert await document.retrieve(reference) == b"cni"

    await document.delete(reference)
    await document.delete(reference)  # idempotent
    with pytest.raises(StorageObjectIntrouvableError):
        await document.retrieve(reference)


async def test_unsafe_keys_are_refused(fake_s3: FakeS3) -> None:
    document = get_storage_backend(_settings(**S3_SETTINGS))
    for key in ("../profile-media/x.png", "/absolu.png", "a//b.png", ""):
        with pytest.raises(ValueError):
            await document.store(b"x", key)


# ------------------------------------------- parcours complets par l'API


@pytest.fixture
def s3_app(db_session: AsyncSession, fake_s3: FakeS3) -> Generator[Settings, None, None]:
    settings = get_settings().model_copy(update={**S3_SETTINGS, "avatar_storage_backend": "s3"})

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_document_upload_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: limiter
    yield settings
    app.dependency_overrides.clear()


async def test_an_identity_document_lives_only_in_the_private_bucket(
    db_session: AsyncSession, fake_s3: FakeS3, s3_app: Settings
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    headers = {"Authorization": f"Bearer {encode_access_token(artisan_user)}"}
    png = make_png()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        uploaded = await http.post(
            "/api/v1/artisans/me/documents",
            headers=headers,
            data={"doc_type": "cni"},
            files={"file": ("cni.png", png, "image/png")},
        )
        document_id = uploaded.json()["id"]
        content = await http.get(
            f"/api/v1/artisans/me/documents/{document_id}/content", headers=headers
        )

    assert uploaded.status_code == 201, uploaded.text
    keys = list(fake_s3.buckets[PRIVATE])
    assert len(keys) == 1 and keys[0].startswith("verification-documents/")
    assert fake_s3.buckets[PUBLIC] == {}
    # Aucune URL publique n'est exposée : la CNI ne sort que par l'endpoint authentifié.
    assert PUBLIC_URL not in uploaded.text
    assert content.status_code == 200
    assert content.content == png


async def test_a_profile_photo_lives_only_in_the_public_bucket(
    db_session: AsyncSession, fake_s3: FakeS3, s3_app: Settings
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    headers = {"Authorization": f"Bearer {encode_access_token(artisan_user)}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await http.post(
            "/api/v1/artisans/me/avatar",
            headers=headers,
            files={"file": ("avatar.png", make_png(), "image/png")},
        )
        second = await http.post(
            "/api/v1/artisans/me/avatar",
            headers=headers,
            files={"file": ("avatar.png", make_png(), "image/png")},
        )

    assert first.status_code == 200, first.text
    avatar_url = second.json()["avatar_url"]
    assert avatar_url.startswith(f"{PUBLIC_URL}/profile-media/")
    assert fake_s3.buckets[PRIVATE] == {}
    # L'ancienne photo, prouvée être la sienne, est effacée du bucket public.
    (key,) = fake_s3.buckets[PUBLIC]
    assert avatar_url.endswith(key.removeprefix("profile-media/"))
    assert fake_s3.buckets[PUBLIC][key].cache_control == PUBLIC_CACHE_CONTROL
