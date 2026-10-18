"""Adressage S3 (S3_FORCE_PATH_STYLE) : path-style exigé par Supabase Storage
et MinIO dès qu'un endpoint personnalisé est configuré.

Le VRAI client boto3 est construit (`build_s3_client`) ; le réseau est
coupé juste avant l'envoi (événement botocore `before-send`) : on lit l'URL
exacte que boto3 aurait appelée. Aucune requête ne sort.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from botocore.awsrequest import AWSPreparedRequest, AWSResponse
from botocore.compat import HTTPHeaders

from app.core.config import Settings
from app.services import storage
from app.services.s3_storage import build_s3_client
from app.services.storage import get_avatar_storage_backend, get_storage_backend

SUPABASE_ENDPOINT = "https://abcdefghijklmnop.storage.supabase.co/storage/v1/s3"
PRIVATE = "teranga-prive"
PUBLIC = "teranga-public"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        "storage_backend": "s3",
        "s3_region": "eu-central-1",
        "s3_access_key_id": "cle-de-test",
        "s3_secret_access_key": "secret-de-test-0123456789",
        "s3_private_bucket": PRIVATE,
        "s3_public_bucket": PUBLIC,
        "s3_public_base_url": f"{SUPABASE_ENDPOINT}/object/public/{PUBLIC}",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


class _EmptyBody:
    """Corps de réponse vide (un PutObject réussi ne renvoie rien)."""

    def stream(self, **_: object) -> Iterator[bytes]:
        yield b""


def _intercept(client: Any) -> list[AWSPreparedRequest]:
    """Coupe le réseau du client ; renvoie la liste des requêtes préparées."""
    sent: list[AWSPreparedRequest] = []

    def _capture(request: AWSPreparedRequest, **_: object) -> AWSResponse:
        sent.append(request)
        return AWSResponse(request.url, 200, HTTPHeaders(), _EmptyBody())

    client.meta.events.register("before-send.s3.*", _capture)
    return sent


def _put_url(settings: Settings, bucket: str = PRIVATE) -> str:
    client = build_s3_client(settings)
    sent = _intercept(client)
    client.put_object(Bucket=bucket, Key="dossier/fichier.png", Body=b"x")
    return sent[0].url


@pytest.fixture
def fresh_client_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(storage, "_s3_clients", {})
    yield


# ------------------------------------------------------------------ réglage


@pytest.mark.parametrize(
    ("endpoint", "forced", "expected"),
    [
        (SUPABASE_ENDPOINT, None, "path"),  # endpoint personnalisé : path-style par défaut
        (SUPABASE_ENDPOINT, True, "path"),
        (SUPABASE_ENDPOINT, False, "virtual"),  # désactivation explicite respectée
        (None, None, None),  # AWS S3 sans réglage : choix de boto3, inchangé
        (None, True, "path"),
    ],
)
def test_effective_addressing_style(
    endpoint: str | None, forced: bool | None, expected: str | None
) -> None:
    settings = _settings(s3_endpoint_url=endpoint, s3_force_path_style=forced)
    assert settings.s3_addressing_style == expected


def test_setting_is_read_from_env_and_empty_means_automatic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "false")
    assert _settings(s3_endpoint_url=SUPABASE_ENDPOINT).s3_addressing_style == "virtual"
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "")
    assert _settings(s3_endpoint_url=SUPABASE_ENDPOINT).s3_addressing_style == "path"


# --------------------------------------------------- URL réellement appelée


def test_custom_endpoint_requests_use_path_style() -> None:
    """Supabase : https://<ref>.storage.supabase.co/storage/v1/s3/<bucket>/<clé>,
    jamais https://<bucket>.<ref>.storage.supabase.co/... (refusé par Supabase)."""
    url = _put_url(_settings(s3_endpoint_url=SUPABASE_ENDPOINT))
    assert url == f"{SUPABASE_ENDPOINT}/{PRIVATE}/dossier/fichier.png"


def test_path_style_can_be_disabled_explicitly() -> None:
    url = _put_url(_settings(s3_endpoint_url=SUPABASE_ENDPOINT, s3_force_path_style=False))
    assert url.startswith(f"https://{PRIVATE}.abcdefghijklmnop.storage.supabase.co/")


def test_aws_without_endpoint_is_unchanged() -> None:
    url = _put_url(_settings(s3_endpoint_url=None))
    assert url == f"https://{PRIVATE}.s3.eu-central-1.amazonaws.com/dossier/fichier.png"


def test_requests_stay_signed_with_sigv4() -> None:
    client = build_s3_client(_settings(s3_endpoint_url=SUPABASE_ENDPOINT))
    sent = _intercept(client)
    client.put_object(Bucket=PRIVATE, Key="a.png", Body=b"x")
    authorization = sent[0].headers["Authorization"]
    if isinstance(authorization, bytes):
        authorization = authorization.decode()
    assert authorization.startswith("AWS4-HMAC-SHA256 ")


# ------------------------------------- séparation privé / public intacte


@pytest.mark.usefixtures("fresh_client_cache")
async def test_private_and_public_stores_still_target_their_own_bucket() -> None:
    """Par les fabriques de l'application : un document d'identité part vers
    le bucket PRIVÉ, une photo de profil vers le bucket PUBLIC, chacun en
    path-style sur l'endpoint Supabase."""
    settings = _settings(s3_endpoint_url=SUPABASE_ENDPOINT)
    sent = _intercept(storage.get_s3_client(settings))

    await get_storage_backend(settings).store(b"cni", "doc-1.png")
    await get_avatar_storage_backend(settings).store(b"photo", "avatar-1.png")

    assert [request.url for request in sent] == [
        f"{SUPABASE_ENDPOINT}/{PRIVATE}/verification-documents/doc-1.png",
        f"{SUPABASE_ENDPOINT}/{PUBLIC}/profile-media/avatar-1.png",
    ]


@pytest.mark.usefixtures("fresh_client_cache")
def test_client_cache_distinguishes_addressing_styles() -> None:
    path = storage.get_s3_client(_settings(s3_endpoint_url=SUPABASE_ENDPOINT))
    virtual = storage.get_s3_client(
        _settings(s3_endpoint_url=SUPABASE_ENDPOINT, s3_force_path_style=False)
    )
    assert path is not virtual
