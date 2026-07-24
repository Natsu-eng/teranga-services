"""Service OTP : génération, hachage, persistance, invalidation, vérification."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.otp import OtpCode
from app.services import otp as otp_service
from tests.factories import unique_phone


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


class _FakeSmsProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))


def test_hash_code_roundtrip_and_never_stores_raw_code() -> None:
    hashed = otp_service.hash_code("123456", iterations=1000)

    assert hashed.startswith("pbkdf2_sha256$1000$")
    assert "123456" not in hashed
    assert otp_service.verify_code_hash("123456", hashed) is True
    assert otp_service.verify_code_hash("654321", hashed) is False


def test_verify_code_hash_rejects_malformed_hash() -> None:
    assert otp_service.verify_code_hash("123456", "pas-un-hash-valide") is False


def test_generate_code_produces_digits_of_requested_length() -> None:
    code = otp_service.generate_code(6)

    assert len(code) == 6
    assert code.isdigit()


async def test_request_otp_persists_hashed_code_and_sends_sms(db_session: AsyncSession) -> None:
    phone = unique_phone()
    sms = _FakeSmsProvider()

    await otp_service.request_otp(db_session, phone, settings=_settings(), sms_provider=sms)

    assert len(sms.sent) == 1
    sent_phone, sent_code = sms.sent[0]
    assert sent_phone == phone

    row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    assert sent_code not in row.code_hash
    assert otp_service.verify_code_hash(sent_code, row.code_hash)
    assert row.consumed_at is None
    assert row.attempts == 0


async def test_request_otp_normalizes_phone_before_persisting(db_session: AsyncSession) -> None:
    sms = _FakeSmsProvider()

    await otp_service.request_otp(
        db_session, "77 123 45 67", settings=_settings(), sms_provider=sms
    )

    row = (
        await db_session.execute(select(OtpCode).where(OtpCode.phone == "+221771234567"))
    ).scalar_one()
    assert row is not None


async def test_request_otp_invalidates_previous_unconsumed_codes(
    db_session: AsyncSession,
) -> None:
    phone = unique_phone()
    sms = _FakeSmsProvider()
    settings = _settings()

    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)
    first_row = (
        await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))
    ).scalar_one()
    assert first_row.consumed_at is None

    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)

    await db_session.refresh(first_row)
    assert first_row.consumed_at is not None


async def test_verify_otp_succeeds_with_correct_code(db_session: AsyncSession) -> None:
    phone = unique_phone()
    sms = _FakeSmsProvider()
    settings = _settings()
    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)
    _, code = sms.sent[0]

    normalized = await otp_service.verify_otp(db_session, phone, code, settings=settings)

    assert normalized == phone
    row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    assert row.consumed_at is not None


async def test_verify_otp_rejects_wrong_code(db_session: AsyncSession) -> None:
    phone = unique_phone()
    sms = _FakeSmsProvider()
    settings = _settings()
    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)

    with pytest.raises(otp_service.OtpInvalideError):
        await otp_service.verify_otp(db_session, phone, "000000", settings=settings)

    row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    assert row.attempts == 1
    assert row.consumed_at is None


async def test_verify_otp_rejects_unknown_phone(db_session: AsyncSession) -> None:
    with pytest.raises(otp_service.OtpIntrouvableError):
        await otp_service.verify_otp(db_session, unique_phone(), "123456", settings=_settings())


async def test_verify_otp_rejects_expired_code(db_session: AsyncSession) -> None:
    phone = unique_phone()
    otp = OtpCode(
        phone=phone,
        code_hash=otp_service.hash_code("123456", iterations=1000),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        attempts=0,
    )
    db_session.add(otp)
    await db_session.flush()

    with pytest.raises(otp_service.OtpExpireError):
        await otp_service.verify_otp(db_session, phone, "123456", settings=_settings())


async def test_verify_otp_rejects_already_consumed_code(db_session: AsyncSession) -> None:
    phone = unique_phone()
    otp = OtpCode(
        phone=phone,
        code_hash=otp_service.hash_code("123456", iterations=1000),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        consumed_at=datetime.now(UTC),
        attempts=0,
    )
    db_session.add(otp)
    await db_session.flush()

    with pytest.raises(otp_service.OtpDejaUtiliseError):
        await otp_service.verify_otp(db_session, phone, "123456", settings=_settings())


async def test_verify_otp_invalidates_code_after_max_attempts(db_session: AsyncSession) -> None:
    phone = unique_phone()
    settings = _settings(otp_max_attempts=2)
    otp = OtpCode(
        phone=phone,
        code_hash=otp_service.hash_code("123456", iterations=1000),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempts=0,
    )
    db_session.add(otp)
    await db_session.flush()

    with pytest.raises(otp_service.OtpInvalideError):
        await otp_service.verify_otp(db_session, phone, "000000", settings=settings)
    with pytest.raises(otp_service.OtpTropTentativesError):
        await otp_service.verify_otp(db_session, phone, "000000", settings=settings)

    # Même avec le bon code : ce code est désormais consommé (épuisé).
    with pytest.raises(otp_service.OtpDejaUtiliseError):
        await otp_service.verify_otp(db_session, phone, "123456", settings=settings)
