import pytest

from app.core.config import Settings
from app.core.phone import PhoneInvalideError, normalize_phone

EXPECTED_E164 = "+221771234567"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw",
    [
        "771234567",
        "77 123 45 67",
        "0771234567",
        "+221771234567",
        "00221771234567",
    ],
)
def test_normalize_phone_accepts_all_equivalent_forms(raw: str) -> None:
    assert normalize_phone(raw, _settings()) == EXPECTED_E164


def test_normalize_phone_is_idempotent() -> None:
    once = normalize_phone("771234567", _settings())
    twice = normalize_phone(once, _settings())
    assert once == twice == EXPECTED_E164


def test_normalize_phone_rejects_empty() -> None:
    with pytest.raises(PhoneInvalideError):
        normalize_phone("   ", _settings())


def test_normalize_phone_rejects_garbage() -> None:
    with pytest.raises(PhoneInvalideError):
        normalize_phone("pas un numero", _settings())


def test_normalize_phone_rejects_too_short_number() -> None:
    with pytest.raises(PhoneInvalideError):
        normalize_phone("123", _settings())


def test_normalize_phone_rejects_disallowed_region() -> None:
    with pytest.raises(PhoneInvalideError):
        normalize_phone("+33612345678", _settings())


def test_normalize_phone_allows_other_region_when_configured() -> None:
    settings = _settings(phone_allowed_regions="SN,FR")
    assert normalize_phone("+33612345678", settings) == "+33612345678"


def test_normalize_phone_uses_configured_default_region() -> None:
    settings = _settings(phone_default_region="FR", phone_allowed_regions="FR")
    assert normalize_phone("0612345678", settings) == "+33612345678"
