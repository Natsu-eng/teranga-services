import logging

import pytest

from app.core.config import Settings
from app.services.sms import (
    ConsoleSmsProvider,
    UnconfiguredSmsProvider,
    get_sms_provider,
)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"database_url": "postgresql+asyncpg://user:pass@localhost:5432/db"}
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


async def test_console_provider_logs_code_in_dev(caplog: pytest.LogCaptureFixture) -> None:
    provider = ConsoleSmsProvider(_settings(app_env="dev"))
    with caplog.at_level(logging.INFO):
        await provider.send_otp("+221771234567", "123456")

    assert "123456" in caplog.text


async def test_console_provider_never_logs_code_outside_dev(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ConsoleSmsProvider(_settings(app_env="staging"))
    with caplog.at_level(logging.DEBUG):
        await provider.send_otp("+221771234567", "654321")

    assert "654321" not in caplog.text


async def test_unconfigured_provider_raises_not_implemented() -> None:
    provider = UnconfiguredSmsProvider()
    with pytest.raises(NotImplementedError):
        await provider.send_otp("+221771234567", "123456")


def test_get_sms_provider_returns_console_by_default() -> None:
    provider = get_sms_provider(_settings())
    assert isinstance(provider, ConsoleSmsProvider)


def test_get_sms_provider_returns_unconfigured_when_selected() -> None:
    provider = get_sms_provider(_settings(sms_provider="unconfigured"))
    assert isinstance(provider, UnconfiguredSmsProvider)
