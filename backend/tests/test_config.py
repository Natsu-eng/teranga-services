import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings


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

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/db"
