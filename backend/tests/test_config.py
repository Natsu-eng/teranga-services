import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings
from app.models.enums import VerificationDocType


def test_settings_requires_database_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "database_url" in str(exc_info.value)


def test_settings_rejects_malformed_database_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "not-a-url")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "malformée" in str(exc_info.value)


def test_settings_rejects_non_asyncpg_driver(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "asyncpg" in str(exc_info.value)


def test_settings_accepts_valid_database_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/db"


def test_settings_requires_jwt_secret(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "jwt_secret" in str(exc_info.value)


def test_settings_rejects_weak_jwt_secret(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "trop-court")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "trop court" in str(exc_info.value)


def _base_settings(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)


def test_settings_default_verification_required_doc_types(monkeypatch: MonkeyPatch) -> None:
    _base_settings(monkeypatch)
    monkeypatch.delenv("VERIFICATION_REQUIRED_DOC_TYPES", raising=False)

    settings = Settings(_env_file=None)

    assert settings.verification_required_doc_types == [
        VerificationDocType.CNI,
        VerificationDocType.SELFIE,
    ]


def test_settings_parses_verification_required_doc_types_from_csv(monkeypatch: MonkeyPatch) -> None:
    _base_settings(monkeypatch)
    monkeypatch.setenv("VERIFICATION_REQUIRED_DOC_TYPES", "cni, accreditation")

    settings = Settings(_env_file=None)

    assert settings.verification_required_doc_types == [
        VerificationDocType.CNI,
        VerificationDocType.ACCREDITATION,
    ]


def test_settings_rejects_unknown_verification_doc_type(monkeypatch: MonkeyPatch) -> None:
    _base_settings(monkeypatch)
    monkeypatch.setenv("VERIFICATION_REQUIRED_DOC_TYPES", "cni,passeport")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_default_pagination_and_search_radius(monkeypatch: MonkeyPatch) -> None:
    _base_settings(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.artisan_search_default_radius_m == 10_000
    assert settings.artisan_search_max_radius_m == 50_000
    assert settings.pagination_page_size_default == 20
    assert settings.pagination_page_size_max == 50
    assert settings.pagination_max_page == 50
