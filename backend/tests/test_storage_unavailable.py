"""Panne du stockage S3 : erreur APPLICATIVE 503, jamais une exception brute.

Cas réel (staging Render) : une erreur boto3 pendant un envoi devenait une
500 produite HORS du middleware CORS ; le navigateur la bloquait et le front
affichait un faux « Impossible de contacter le serveur ». Désormais :
`StockageIndisponibleError` -> 503 JSON avec les en-têtes CORS, cause exacte
dans les journaux (jamais de clé ni de contenu).
"""

import logging
from collections.abc import AsyncGenerator, Iterator
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.repositories import conversations as conversations_repository
from app.services import conversation_attachments, storage
from app.services.profile_media import discard_obsolete_media
from app.services.rate_limit import (
    SlidingWindowRateLimiter,
    get_document_upload_rate_limiter,
    get_profile_media_upload_rate_limiter,
)
from app.services.s3_storage import S3StorageBackend
from app.services.storage import StockageIndisponibleError, StorageObjectIntrouvableError
from tests.factories import make_artisan_profile, make_engagement, make_user
from tests.images import make_png

SECRET = "secret-de-test-0123456789abcdef"
S3_SETTINGS: dict[str, object] = {
    "storage_backend": "s3",
    "avatar_storage_backend": "s3",
    "s3_endpoint_url": "https://ref.storage.supabase.co/storage/v1/s3",
    "s3_region": "eu-central-1",
    "s3_access_key_id": "cle-de-test",
    "s3_secret_access_key": SECRET,
    "s3_private_bucket": "documents",
    "s3_public_bucket": "media",
    "s3_public_base_url": "https://ref.supabase.co/storage/v1/object/public/media",
}


def _client_error(code: str, status: int) -> ClientError:
    # Réponse partielle (seuls les champs lus par le code) : cast pour mypy.
    response = {
        "Error": {"Code": code, "Message": "refusé"},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(cast(Any, response), "PutObject")


class FailingS3:
    """Client S3 qui échoue comme le ferait Supabase (refus, réseau)."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def put_object(self, **kwargs: Any) -> Any:
        raise self.error

    def get_object(self, **kwargs: Any) -> Any:
        raise self.error

    def delete_object(self, **kwargs: Any) -> Any:
        raise self.error


def _backend(error: Exception) -> S3StorageBackend:
    return S3StorageBackend(FailingS3(error), bucket="documents", prefix="docs", public=False)


# ------------------------------------------------------- couche stockage


@pytest.mark.parametrize(
    "error",
    [_client_error("AccessDenied", 403), EndpointConnectionError(endpoint_url="https://x")],
)
async def test_provider_failures_become_an_application_error(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    backend = _backend(error)
    with caplog.at_level(logging.ERROR, logger="app.services.s3_storage"):
        for call in (
            backend.store(b"x", "a.png"),
            backend.retrieve("a.png"),
            backend.delete("a.png"),
        ):
            with pytest.raises(StockageIndisponibleError) as exc:
                await call
            assert exc.value.status_code == 503
            assert exc.value.code == "STOCKAGE_INDISPONIBLE"
    # La cause exacte est journalisée (opération, bucket, code), jamais un secret.
    assert "PutObject" in caplog.text and "'documents'" in caplog.text
    if isinstance(error, ClientError):
        assert "AccessDenied (HTTP 403)" in caplog.text
    assert SECRET not in caplog.text


async def test_a_missing_object_is_still_reported_as_missing() -> None:
    with pytest.raises(StorageObjectIntrouvableError):
        await _backend(_client_error("NoSuchKey", 404)).retrieve("a.png")


def test_a_client_refused_by_boto3_becomes_an_application_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refuse(_settings: Settings) -> None:
        raise ValueError("Invalid endpoint: https://exemple\n")

    monkeypatch.setattr(storage, "_s3_clients", {})
    monkeypatch.setattr("app.services.s3_storage.build_s3_client", _refuse)
    settings = get_settings().model_copy(update=S3_SETTINGS)

    with pytest.raises(StockageIndisponibleError):
        storage.get_s3_client(settings)


# ------------------------------------------- nettoyages « au mieux »


async def test_discarding_an_old_photo_never_fails_the_committed_update() -> None:
    await discard_obsolete_media(_backend(_client_error("AccessDenied", 403)), "ancienne.png")


async def test_orphan_cleanup_never_hides_the_original_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Message avec image : si l'écriture en base échoue et que le stockage
    échoue aussi au nettoyage, c'est l'erreur d'ORIGINE qui remonte."""
    engagement = await make_engagement(db_session)

    class _StoreThenFail:
        async def store(self, content: bytes, key: str) -> str:
            return key

        async def retrieve(self, reference: str) -> bytes:
            raise AssertionError("inutile ici")

        async def delete(self, reference: str) -> None:
            raise StockageIndisponibleError()

    async def _db_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("écriture en base impossible")

    monkeypatch.setattr(conversations_repository, "add_message", _db_failure)

    with pytest.raises(RuntimeError, match="écriture en base impossible"):
        await conversation_attachments.send_image_message(
            db_session,
            conversation_id=engagement.conversation.id,
            sender=engagement.client,
            content=make_png(),
            caption="",
            settings=get_settings(),
            storage=_StoreThenFail(),
        )


# --------------------------------------------------------- par l'API


@pytest.fixture
def failing_storage_app(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Settings]:
    settings = get_settings().model_copy(update=S3_SETTINGS)
    failing = FailingS3(_client_error("NoSuchBucket", 404))
    monkeypatch.setattr(storage, "get_s3_client", lambda _settings: failing)

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_document_upload_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: limiter
    yield settings
    app.dependency_overrides.clear()


@pytest.mark.usefixtures("failing_storage_app")
@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/api/v1/artisans/me/documents", {"doc_type": "cni"}),
        ("/api/v1/artisans/me/cover", None),
    ],
)
async def test_an_upload_during_a_storage_outage_gets_a_503_the_browser_can_read(
    db_session: AsyncSession, path: str, data: dict[str, str] | None
) -> None:
    origin = get_settings().cors_origins[0]
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            path,
            headers={
                "Authorization": f"Bearer {encode_access_token(artisan_user)}",
                "Origin": origin,
            },
            data=data,
            files={"file": ("photo.png", make_png(), "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STOCKAGE_INDISPONIBLE"
    # L'en-tête CORS est là : le front lit le message au lieu d'un faux échec réseau.
    assert response.headers["access-control-allow-origin"] == origin
