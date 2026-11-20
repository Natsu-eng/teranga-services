"""Réglages de production (DEPLOYMENT.md) : environnement en ensemble fermé,
fail-fast au démarrage en production, aucun changement pour le dev.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings, normalize_environment_name
from tests.deployed_settings import DEPLOYED_REQUIRED

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Configuration de production COMPLÈTE et réaliste, sauf le fournisseur SMS
# (aucun n'est encore branché : voir le test dédié plus bas).
STRONG_SECRET = "Q2x9mV7pLr4tZb8NwK3sHc6YdF1gJ5uEaT0oRiXy"
PRODUCTION: dict[str, object] = {
    "environment": "production",
    "database_url": "postgresql+asyncpg://teranga:S9vR2kLq7ZtW4mPx@postgres.railway.internal:5432/railway",
    "jwt_secret": STRONG_SECRET,
    "payment_provider": "disabled",
    "frontend_public_base_url": "https://teranga.sn",
    "backend_public_base_url": "https://api.teranga.sn",
    "cors_origins": ["https://teranga.sn"],
    "trusted_proxy_hops": 1,
    "storage_backend": "s3",
    "s3_endpoint_url": "https://compte.r2.cloudflarestorage.com",
    "s3_access_key_id": "cle-acces-de-test",
    "s3_secret_access_key": "k8Vq2LrT9mZx4Wn7Pb3Hs6Yc1Fd5Gj0Ue",
    "s3_private_bucket": "teranga-prive",
    "s3_public_bucket": "teranga-public",
    "s3_public_base_url": "https://media.teranga.sn",
    **DEPLOYED_REQUIRED,
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**PRODUCTION, **overrides})  # type: ignore[arg-type]


def _problems(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(exc.value)


def test_development_starts_with_only_database_and_jwt(monkeypatch: MonkeyPatch) -> None:
    """Le dev démarre comme avant : aucune variable nouvelle exigée (pas de
    Redis, pas de S3, sandbox de paiement, SMS console)."""
    for name in ("ENVIRONMENT", "APP_ENV", "REDIS_URL", "STORAGE_BACKEND", "PAYMENT_PROVIDER"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        jwt_secret="a" * 32,
    )

    assert settings.environment == "development"
    assert settings.is_local and not settings.is_production
    assert settings.rate_limit_backend == "memory"
    assert settings.payment_provider == "sandbox"
    assert settings.sms_provider == "console"
    assert settings.storage_backend == "local"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("dev", "development"), ("prod", "production"), ("Staging", "staging"), ("test", "test")],
)
def test_environment_accepts_the_closed_set_and_legacy_values(raw: str, expected: str) -> None:
    assert normalize_environment_name(raw) == expected


def test_unknown_environment_is_refused_with_the_accepted_values() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(environment="prodution")
    assert "development, test, staging, production" in _problems(exc)


def test_environment_variable_wins_over_the_legacy_name(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        jwt_secret="a" * 32,
        payment_provider="disabled",
        **DEPLOYED_REQUIRED,  # type: ignore[arg-type]
    )
    assert settings.environment == "staging"


def test_production_lists_every_dev_leftover_at_once() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(
            jwt_secret="change-me-change-me-change-me-change-me",
            database_url="postgresql+asyncpg://user:password@localhost:5432/teranga",
            payment_provider="sandbox",
            sms_provider="console",
            frontend_public_base_url="http://localhost:3000",
            backend_public_base_url="http://localhost:8000",
        )
    message = _problems(exc)
    for expected in (
        "JWT_SECRET est une valeur d'exemple",
        "DATABASE_URL pointe vers une base locale",
        "DATABASE_URL n'a pas de mot de passe réel",
        "PAYMENT_PROVIDER=sandbox est interdit en production",
        "SMS_PROVIDER=console est interdit en production",
        "FRONTEND_PUBLIC_BASE_URL doit être l'URL publique HTTPS",
        "BACKEND_PUBLIC_BASE_URL doit être l'URL publique HTTPS",
    ):
        assert expected in message


def test_production_requires_the_jwt_secret(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    config = {key: value for key, value in PRODUCTION.items() if key != "jwt_secret"}
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **config)  # type: ignore[arg-type]
    assert "jwt_secret" in _problems(exc)


def test_production_mistral_requires_its_key() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(ai_triage_provider="mistral", mistral_api_key="")
    assert "AI_TRIAGE_PROVIDER=mistral exige MISTRAL_API_KEY" in _problems(exc)


def test_complete_production_config_is_blocked_only_by_the_missing_sms_provider() -> None:
    """Constat honnête : tout est prêt sauf l'envoi des SMS. Aucun
    fournisseur réel n'existe encore ; la prod refuse donc de démarrer
    plutôt que de laisser des utilisateurs sans code de connexion."""
    with pytest.raises(ValidationError) as exc:
        _settings(sms_provider="unconfigured")
    message = _problems(exc)
    assert "SMS_PROVIDER=unconfigured" in message
    assert message.count("\n- ") == 1


def test_app_startup_fails_cleanly_in_production_without_secrets() -> None:
    """Démarrage RÉEL simulé (import de l'application dans un processus
    neuf) avec ENVIRONMENT=production et la configuration de dev : il échoue
    avant de servir quoi que ce soit, en nommant le problème."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("JWT_SECRET", "DATABASE_URL", "APP_ENV")
    }
    env.update(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/teranga",
        PAYMENT_PROVIDER="disabled",
    )
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR / "tests",  # aucun .env lu : seule la configuration ci-dessus compte
        env={**env, "PYTHONPATH": str(BACKEND_DIR)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode != 0
    assert "jwt_secret" in result.stderr


# ---------------------------------------------------------------------- CORS


@pytest.mark.parametrize("origins", [["*"], ["https://*.teranga.sn"]])
def test_cors_wildcard_is_refused_everywhere(origins: list[str]) -> None:
    with pytest.raises(ValidationError, match="joker"):
        _settings(environment="development", cors_origins=origins)


@pytest.mark.parametrize("origin", ["https://teranga.sn/", "https://teranga.sn/app", "teranga.sn"])
def test_cors_entries_must_be_bare_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="n'est pas une origine"):
        _settings(environment="development", cors_origins=[origin])


def test_production_cors_must_be_https_and_include_the_front() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(sms_provider="console", cors_origins=["http://localhost:3000"])
    message = _problems(exc)
    assert "CORS_ORIGINS : 'http://localhost:3000' doit être une origine HTTPS publique" in message
    assert "CORS_ORIGINS doit contenir l'origine du front ('https://teranga.sn')" in message


def test_same_origin_deployment_needs_no_cors() -> None:
    """Front et API derrière la même origine (reverse proxy) : CORS vide admis."""
    with pytest.raises(ValidationError) as exc:
        _settings(
            sms_provider="unconfigured",
            cors_origins=[],
            frontend_public_base_url="https://teranga.sn",
            backend_public_base_url="https://teranga.sn",
        )
    assert "CORS_ORIGINS" not in _problems(exc)


def test_production_requires_an_explicit_trusted_proxy_count() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(sms_provider="console", trusted_proxy_hops=None)
    assert "TRUSTED_PROXY_HOPS doit être renseigné" in _problems(exc)
