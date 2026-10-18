"""Variables S3 collées dans un tableau de bord (Render, Railway) : nettoyées,
puis validées AU DÉMARRAGE avec la liste de toutes les variables en cause.

Cas réel (staging Render) : un retour à la ligne final dans S3_ENDPOINT_URL,
invisible à l'écran, faisait refuser le client par boto3 (« Invalid
endpoint ») au premier envoi de fichier, alors que le service démarrait
« sain ». Désormais : nettoyé s'il est en bordure, refus au démarrage s'il
est à l'intérieur -- jamais une panne découverte par un testeur.
"""

import pytest
from botocore.utils import is_valid_endpoint_url
from pydantic import ValidationError

from app.core.config import Settings, clean_setting_value, is_valid_s3_endpoint
from app.services.s3_storage import build_s3_client

ENDPOINT = "https://ffhmotcgodcgalfhnnqx.storage.supabase.co/storage/v1/s3"
ACCESS_KEY = "cle-acces-0123456789"
SECRET = "secret-de-test-0123456789abcdef"
VALUES: dict[str, str] = {
    "s3_endpoint_url": ENDPOINT,
    "s3_region": "eu-central-1",
    "s3_access_key_id": ACCESS_KEY,
    "s3_secret_access_key": SECRET,
    "s3_private_bucket": "documents",
    "s3_public_bucket": "media",
    "s3_public_base_url": "https://ffhmotcgodcgalfhnnqx.supabase.co/storage/v1/object/public/media",
}
# Bordures typiques d'un copier-coller : retour à la ligne (Entrée), CRLF,
# tabulation, espace insécable, BOM, espace de largeur nulle.
DIRTY_EDGES = ("\n", "\r\n", " \t", "\u00a0", "\ufeff", "\u200b \n")


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        "storage_backend": "s3",
        **VALUES,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def _errors(**overrides: object) -> str:
    with pytest.raises(ValidationError) as exc:
        _settings(**overrides)
    return str(exc.value)


# ------------------------------------------------------------- nettoyage


def test_the_render_case_trailing_newline_in_endpoint_is_cleaned() -> None:
    settings = _settings(s3_endpoint_url=ENDPOINT + "\n")
    assert settings.s3_endpoint_url == ENDPOINT
    # Le client boto3 se construit : plus d'« Invalid endpoint » au premier envoi.
    build_s3_client(settings)


@pytest.mark.parametrize("field", sorted(VALUES))
@pytest.mark.parametrize("edge", DIRTY_EDGES)
def test_every_s3_variable_is_cleaned_at_both_edges(field: str, edge: str) -> None:
    settings = _settings(**{field: f"{edge}{VALUES[field]}{edge}"})
    assert getattr(settings, field) == VALUES[field]


def test_cleaning_reads_real_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT_URL", ENDPOINT + "\r\n")
    monkeypatch.setenv("S3_PRIVATE_BUCKET", " documents\n")
    kwargs: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        "storage_backend": "s3",
        **{k: v for k, v in VALUES.items() if k not in ("s3_endpoint_url", "s3_private_bucket")},
    }
    settings = Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]
    assert (settings.s3_endpoint_url, settings.s3_private_bucket) == (ENDPOINT, "documents")


def test_blank_after_cleaning_means_missing() -> None:
    message = _errors(s3_access_key_id="\n \u200b", s3_private_bucket="\ufeff")
    assert "Stockage S3 incomplet, à renseigner : S3_ACCESS_KEY_ID, S3_PRIVATE_BUCKET." in message


def test_clean_setting_value_never_touches_the_inside() -> None:
    assert clean_setting_value(" \u200bab c\u200b\n") == "ab c"


# --------------------------------------------- validation au démarrage


def test_invisible_character_inside_the_endpoint_is_refused_and_shown() -> None:
    message = _errors(s3_endpoint_url=ENDPOINT.replace(".storage", "\u200b.storage"))
    assert "S3_ENDPOINT_URL n'est pas une URL d'endpoint valide" in message
    assert "\\u200b" in message  # repr() rend le caractère visible


@pytest.mark.parametrize(
    "endpoint",
    [
        f'"{ENDPOINT}"',
        "ffhmotcgodcgalfhnnqx.storage.supabase.co",
        "ftp://h.example.com/s3",
        "https://",
        "https://hôte-accentué.example/s3",
        "https://h.example.com:port/s3",
    ],
)
def test_malformed_endpoints_are_refused(endpoint: str) -> None:
    assert "S3_ENDPOINT_URL" in _errors(s3_endpoint_url=endpoint)


def test_all_problems_are_listed_at_once_without_any_secret() -> None:
    message = _errors(
        s3_endpoint_url=ENDPOINT.replace("supabase", "supa base"),
        s3_region="eu central 1",
        s3_access_key_id="cle acces",
        s3_secret_access_key="secret avec\tblanc-0123456789",
        s3_private_bucket="docu/ments",
        s3_public_base_url="media.example.com",
    )
    assert message.count("\n- ") >= 6
    for name in (
        "S3_ENDPOINT_URL",
        "S3_REGION",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "S3_PRIVATE_BUCKET",
        "S3_PUBLIC_BASE_URL",
    ):
        assert name in message, name
    # Jamais une clé ni un secret dans le message (journaux de démarrage).
    assert "cle acces" not in message
    assert "secret avec" not in message
    assert "valeur non affichée" in message


def test_buckets_must_still_differ() -> None:
    assert "deux buckets différents" in _errors(s3_public_bucket="documents")


def test_local_storage_ignores_s3_variables_as_before() -> None:
    """Développement (stockage local) : les variables S3 ne sont pas vérifiées."""
    settings = _settings(storage_backend="local", s3_endpoint_url="pas une url", s3_region="?")
    assert settings.storage_backend == "local"


# ------------------------------- jamais d'écart avec la règle de botocore


@pytest.mark.parametrize(
    "endpoint",
    [
        ENDPOINT,
        "https://compte.r2.cloudflarestorage.com",
        "http://127.0.0.1:54321/storage/v1/s3",
        "http://localhost:9000",
        "https://s3.eu-central-1.amazonaws.com",
        "https://h.example.com.",
        f"{ENDPOINT}\n",
        f'"{ENDPOINT}"',
        "\ufeff" + ENDPOINT,
        ENDPOINT.replace(".storage", "\u200b.storage"),
        "https://-tiret.example.com",
        "https://hôte.example",
    ],
)
def test_an_endpoint_accepted_at_startup_is_always_accepted_by_botocore(endpoint: str) -> None:
    """Propriété clé : si le démarrage accepte l'endpoint, boto3 aussi -- le
    client ne peut plus être refusé au premier envoi."""
    if is_valid_s3_endpoint(endpoint):
        assert is_valid_endpoint_url(endpoint)
        build_s3_client(_settings(s3_endpoint_url=endpoint))
