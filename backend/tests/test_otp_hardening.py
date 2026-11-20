"""Durcissement OTP (lot `feat/hardening-masking-otp`) : clé HMAC, essais
atomiques, limites par numéro / IP / jour, plafond global de SMS, réglages
exigés hors développement.

Les tests HTTP utilisent l'application réelle (ASGI) et la base de dev dans
une transaction annulée ; les compteurs en mémoire sont neufs à chaque test
(conftest.py). Le test de CONCURRENCE, lui, a besoin de vraies transactions
parallèles : il écrit ses propres lignes `otp_code` (numéro unique) et les
supprime à la fin, sans toucher à rien d'autre.
"""

import asyncio
import logging
import secrets
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import OTP_HMAC_KEY_MIN_LENGTH, Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.otp import OtpCode
from app.services import admin_notifications
from app.services import auth as auth_service
from app.services import otp as otp_service
from app.services.email import OutgoingEmail
from app.services.otp_sms_budget import SmsBudgetAlert, reserve_sms
from app.services.rate_limit import SlidingWindowRateLimiter
from tests.deployed_settings import DEPLOYED_REQUIRED
from tests.factories import make_user, unique_phone
from tests.test_production_settings import PRODUCTION
from tests.test_termii import TERMII

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _plain(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


class RecordingProvider:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)


# ------------------------------------------------------- réglages exigés


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_require_the_hmac_key_and_proxy_hops(environment: str) -> None:
    base = {**PRODUCTION, **TERMII} if environment == "production" else {}
    with pytest.raises(ValidationError) as exc:
        _plain(
            **{**base, "environment": environment, "otp_hmac_key": None, "trusted_proxy_hops": None}
        )
    message = str(exc.value)
    assert "OTP_HMAC_KEY doit être renseignée" in message
    assert "TRUSTED_PROXY_HOPS doit être renseigné" in message


def test_staging_starts_with_both_settings() -> None:
    assert _plain(environment="staging", **DEPLOYED_REQUIRED).environment == "staging"


def test_development_needs_no_key_and_uses_a_process_key() -> None:
    settings = _plain()
    assert settings.otp_hmac_key is None
    assert len(otp_service.otp_hmac_key(settings)) == 32


def test_a_short_key_is_refused_without_being_shown() -> None:
    short = secrets.token_urlsafe(8)
    with pytest.raises(ValidationError) as exc:
        _plain(otp_hmac_key=short)
    assert f"{OTP_HMAC_KEY_MIN_LENGTH} minimum" in str(exc.value)
    assert short not in str(exc.value)


def test_a_key_with_a_space_inside_is_refused_without_being_shown() -> None:
    broken = secrets.token_urlsafe(20) + " " + secrets.token_urlsafe(20)
    with pytest.raises(ValidationError) as exc:
        _plain(otp_hmac_key=broken)
    assert "valeur non affichée" in str(exc.value)
    assert broken not in str(exc.value)


def test_a_pasted_key_is_cleaned() -> None:
    key = secrets.token_urlsafe(32)
    assert _plain(otp_hmac_key=f" {key}\r\n").otp_hmac_key == key


def test_staging_refuses_a_placeholder_key() -> None:
    with pytest.raises(ValidationError, match="OTP_HMAC_KEY est une valeur d'exemple"):
        _plain(environment="staging", trusted_proxy_hops=1, otp_hmac_key="change-me-" * 4)


def test_the_script_prints_a_long_enough_key_and_writes_nothing() -> None:
    before = set(BACKEND_DIR.iterdir())
    result = subprocess.run(
        [sys.executable, "scripts/generate_otp_hmac_key.py"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("OTP_HMAC_KEY="))
    key = line.removeprefix("OTP_HMAC_KEY=")
    assert len(key) >= OTP_HMAC_KEY_MIN_LENGTH
    assert _plain(environment="staging", trusted_proxy_hops=1, otp_hmac_key=key).otp_hmac_key
    assert set(BACKEND_DIR.iterdir()) == before


# --------------------------------------------------- ancien format refusé


async def test_a_code_hashed_with_the_old_pbkdf2_format_is_refused_as_expired(
    db_session: AsyncSession,
) -> None:
    phone = unique_phone()
    otp = OtpCode(
        phone=phone,
        code_hash="pbkdf2_sha256$600000$" + "00" * 16 + "$" + "11" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempts=0,
    )
    db_session.add(otp)
    await db_session.flush()

    with pytest.raises(otp_service.OtpExpireError):
        await otp_service.verify_otp(db_session, phone, "123456", settings=_plain())
    await db_session.refresh(otp)
    assert otp.consumed_at is not None


# ------------------------------------------------- essais atomiques (concurrence)


async def _concurrent_verify(code: str, attempts: int, *, max_attempts: int) -> list[str]:
    """`attempts` vérifications SIMULTANÉES, chacune dans sa transaction."""
    settings = get_settings().model_copy(update={"otp_max_attempts": max_attempts})
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    phone = unique_phone()
    key = otp_service.otp_hmac_key(settings)
    try:
        async with AsyncSession(engine) as setup:
            setup.add(
                OtpCode(
                    phone=phone,
                    code_hash=otp_service.hash_code("123456", key=key),
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                    attempts=0,
                    created_at=datetime.now(UTC),
                )
            )
            await setup.commit()

        start = asyncio.Event()

        async def one() -> str:
            async with AsyncSession(engine) as session:
                await start.wait()
                try:
                    await otp_service.verify_otp(session, phone, code, settings=settings)
                except AppError as error:
                    await session.commit()  # comme la route : l'essai reste compté
                    return error.code
                await session.commit()
                return "OK"

        tasks = [asyncio.create_task(one()) for _ in range(attempts)]
        await asyncio.sleep(0.1)
        start.set()
        outcomes = await asyncio.gather(*tasks)

        async with AsyncSession(engine) as check:
            stored = (
                await check.execute(select(OtpCode).where(OtpCode.phone == phone))
            ).scalar_one()
            outcomes.append(f"attempts={stored.attempts}")
        return outcomes
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(OtpCode).where(OtpCode.phone == phone))
        await engine.dispose()


async def test_concurrent_wrong_codes_never_get_more_than_max_attempts() -> None:
    outcomes = await _concurrent_verify("000000", 15, max_attempts=3)

    assert outcomes[-1] == "attempts=3"  # jamais plus que le maximum
    results = outcomes[:-1]
    assert results.count("OTP_INVALIDE") == 2
    assert results.count("OTP_TROP_TENTATIVES") == 13


async def test_concurrent_right_codes_open_exactly_one_session() -> None:
    outcomes = await _concurrent_verify("123456", 10, max_attempts=5)

    results = outcomes[:-1]
    assert results.count("OK") == 1
    assert results.count("OTP_DEJA_UTILISE") == 9


# ------------------------------------------------------- limites HTTP


@pytest.fixture
def http_app(db_session: AsyncSession) -> Generator[None, None, None]:
    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"admin_notification_emails": []}
    )
    yield
    app.dependency_overrides.clear()


def _override(**changes: Any) -> None:
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(update=changes)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _request(http: AsyncClient, phone: str) -> Response:
    return await http.post("/api/v1/auth/request-otp", json={"phone": phone})


async def _verify(http: AsyncClient, phone: str, code: str = "000000") -> Response:
    return await http.post(
        "/api/v1/auth/verify-otp", json={"phone": phone, "code": code, "intent": "login"}
    )


@pytest.mark.usefixtures("http_app")
async def test_request_otp_has_a_daily_limit_per_phone() -> None:
    _override(rate_limit_otp_per_phone_max=10, rate_limit_otp_per_phone_daily_max=2)
    phone = unique_phone()
    async with _client() as http:
        statuses = [(await _request(http, phone)).status_code for _ in range(3)]
    assert statuses == [204, 204, 429]


@pytest.mark.usefixtures("http_app")
async def test_request_otp_has_a_daily_limit_per_ip() -> None:
    _override(rate_limit_otp_per_ip_max=10, rate_limit_otp_per_ip_daily_max=2)
    async with _client() as http:
        statuses = [(await _request(http, unique_phone())).status_code for _ in range(3)]
    assert statuses == [204, 204, 429]


@pytest.mark.usefixtures("http_app")
async def test_verify_otp_is_rate_limited_per_phone() -> None:
    _override(rate_limit_otp_verify_per_phone_max=2)
    phone = unique_phone()
    async with _client() as http:
        await _request(http, phone)
        statuses = [(await _verify(http, phone)).status_code for _ in range(3)]
    assert statuses == [400, 400, 429]


@pytest.mark.usefixtures("http_app")
async def test_verify_otp_is_rate_limited_per_ip() -> None:
    _override(rate_limit_otp_verify_per_ip_max=2)
    async with _client() as http:
        statuses = [(await _verify(http, unique_phone())).status_code for _ in range(3)]
    assert statuses[-1] == 429
    assert statuses[:2] == [400, 400]


# ------------------------------------------------------ plafond global de SMS


@pytest.mark.usefixtures("http_app")
async def test_the_global_hourly_cap_refuses_clearly(db_session: AsyncSession) -> None:
    _override(otp_sms_global_max_per_hour=2)
    phones = [unique_phone() for _ in range(3)]
    async with _client() as http:
        responses = [await _request(http, phone) for phone in phones]

    assert [r.status_code for r in responses] == [204, 204, 503]
    assert responses[2].json()["error"]["code"] == "ENVOI_CODES_SATURE"
    # Aucun code créé pour la demande refusée.
    refused = await db_session.scalar(select(OtpCode.id).where(OtpCode.phone == phones[2]))
    assert refused is None


@pytest.mark.usefixtures("http_app")
async def test_existing_sessions_are_untouched_when_the_cap_is_reached(
    db_session: AsyncSession,
) -> None:
    _override(otp_sms_global_max_per_hour=1)
    user = await make_user(db_session, role=Role.CLIENT)
    _access, refresh = await auth_service.issue_token_pair(db_session, user)
    async with _client() as http:
        await _request(http, unique_phone())
        refused = await _request(http, unique_phone())
        refreshed = await http.post("/api/v1/auth/refresh", json={"refresh": refresh})

    assert refused.status_code == 503
    assert refreshed.status_code == 200


@pytest.mark.usefixtures("http_app")
async def test_test_mode_numbers_do_not_consume_the_global_cap() -> None:
    test_phone = unique_phone()
    _override(
        environment="staging",
        otp_test_whitelist=[test_phone],
        otp_test_code="123456",
        otp_sms_global_max_per_hour=1,
        **DEPLOYED_REQUIRED,
    )
    async with _client() as http:
        test_statuses = [(await _request(http, test_phone)).status_code for _ in range(2)]
        real_first = await _request(http, unique_phone())
        real_second = await _request(http, unique_phone())

    assert test_statuses == [204, 204]
    assert real_first.status_code == 204
    assert real_second.status_code == 503


@pytest.mark.usefixtures("http_app")
async def test_admins_are_alerted_at_the_threshold_then_at_the_cap_once_each(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)
    _override(
        admin_notification_emails=["admin@teranga.example"],
        otp_sms_global_max_per_hour=100,
        otp_sms_global_max_per_day=4,
        otp_sms_alert_threshold_percent=50,
    )
    phones = [unique_phone() for _ in range(6)]
    with caplog.at_level(logging.INFO):
        async with _client() as http:
            statuses = [(await _request(http, phone)).status_code for phone in phones]

    assert statuses == [204, 204, 204, 204, 503, 503]
    subjects = [email.subject for email in provider.sent]
    assert subjects == [
        "Téranga : 50 % du plafond journalier de SMS de code atteint",
        "Téranga : plafond journalier de SMS de code atteint",
    ]
    for email in provider.sent:
        for phone in phones:
            assert phone not in email.body and phone[-9:] not in email.body
    assert "Plafond global de SMS de code atteint : demande refusée." in caplog.text


async def test_the_budget_alerts_only_once_per_window() -> None:
    settings = _plain(otp_sms_global_max_per_hour=100, otp_sms_global_max_per_day=10)
    limiter = SlidingWindowRateLimiter()
    alerts = [(await reserve_sms(limiter, settings)).alert for _ in range(12)]

    # Seuil (50 % de 10 = 5) au 5e envoi, plafond au 10e, rien d'autre.
    assert alerts[4] is SmsBudgetAlert.THRESHOLD
    assert alerts[9] is SmsBudgetAlert.FULL
    assert [a for i, a in enumerate(alerts) if i not in (4, 9)] == [None] * 10


async def test_an_hourly_refusal_does_not_burn_the_daily_budget() -> None:
    settings = _plain(otp_sms_global_max_per_hour=1, otp_sms_global_max_per_day=3)
    limiter = SlidingWindowRateLimiter()
    first = await reserve_sms(limiter, settings)
    refused = [await reserve_sms(limiter, settings) for _ in range(5)]

    assert first.allowed
    assert not any(decision.allowed for decision in refused)
    # Le compteur journalier n'a enregistré que l'envoi accepté.
    assert await limiter.check("global:day", max_hits=3, window_seconds=86_400)
    assert await limiter.check("global:day", max_hits=3, window_seconds=86_400)
    assert not await limiter.check("global:day", max_hits=3, window_seconds=86_400)
