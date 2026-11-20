"""Livraison des codes OTP par Termii (app/services/sms_termii.py).

Aucun réseau : un faux serveur Termii (`httpx.MockTransport`) répond selon
un scénario et enregistre chaque requête -- on prouve le chemin et le corps
EXACTS envoyés, la sélection de canal, les essais, le budget de temps, le
routage « liste de test -> code de test / sinon -> Termii » et la réponse
503 lisible par le navigateur en cas d'échec.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Iterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import app
from app.services import otp as otp_service
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter
from app.services.sms import OtpEnvoiIndisponibleError, get_sms_provider
from app.services.sms_termii import TERMII_SEND_PATH, TermiiSmsProvider, mask_phone
from tests.deployed_settings import DEPLOYED_REQUIRED
from tests.factories import unique_phone
from tests.test_production_settings import PRODUCTION

API_KEY = "TLtermiiCleSecrete0123456789"
BASE_URL = "https://compte.termii.example.com"
SENDER = "Teranga"
TEST_CODE = "482913"
TERMII: dict[str, object] = {
    "sms_provider": "termii",
    "termii_api_key": API_KEY,
    "termii_sender_id": SENDER,
    "termii_base_url": BASE_URL,
}
OK = {"code": "ok", "message_id": "1", "message": "Successfully Sent"}


def _settings(environment: str = "staging", **overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "environment": environment,
        "payment_provider": "disabled",
        **TERMII,
        **DEPLOYED_REQUIRED,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


class FakeTermii:
    """Faux serveur : rejoue `script` (une réponse ou une exception par
    requête, la dernière se répète) et enregistre chaque requête."""

    def __init__(self, *script: httpx.Response | Exception) -> None:
        self.script = list(script) or [httpx.Response(200, json=OK)]
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        return step

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]

    def provider(self, settings: Settings) -> TermiiSmsProvider:
        return TermiiSmsProvider(settings, transport=httpx.MockTransport(self.handler))


def _response(status: int, body: object = None) -> httpx.Response:
    return httpx.Response(status, json=body if body is not None else {"code": "error"})


# -------------------------------------------------------------- configuration


def test_termii_requires_its_three_variables_listed_at_once() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(termii_api_key="", termii_sender_id=None, termii_base_url="\n")
    assert (
        "Termii incomplet, à renseigner : TERMII_API_KEY, TERMII_SENDER_ID, TERMII_BASE_URL."
        in str(exc.value)
    )


def test_pasted_values_are_cleaned() -> None:
    settings = _settings(termii_base_url=BASE_URL + "\n", termii_api_key=f" {API_KEY}\r\n")
    assert (settings.termii_base_url, settings.termii_api_key) == (BASE_URL, API_KEY)


def test_invalid_values_are_refused_without_ever_showing_the_key() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(
            termii_api_key="cle avec espace",
            termii_sender_id="Expediteur trop long",
            termii_base_url="http://compte.termii.example.com",
        )
    message = str(exc.value)
    for name in ("TERMII_API_KEY", "TERMII_SENDER_ID", "TERMII_BASE_URL"):
        assert name in message, name
    assert "cle avec espace" not in message


def test_http_base_url_is_accepted_only_on_a_dev_machine() -> None:
    assert _settings("development", termii_base_url="http://localhost:8099").termii_base_url


@pytest.mark.parametrize("channel", ["whatsapp", "whatsapp_then_sms"])
def test_whatsapp_code_must_have_4_to_6_digits(channel: str) -> None:
    with pytest.raises(ValidationError, match="4 à 6"):
        _settings(otp_channel=channel, otp_code_length=8)


def test_total_budget_stays_under_the_front_timeout() -> None:
    settings = _settings()
    # Délai du front pour un appel court : 10 s (frontend/src/lib/api/http.ts).
    assert settings.termii_timeout_seconds <= settings.termii_total_timeout_seconds < 10


def test_timeout_larger_than_budget_is_refused() -> None:
    with pytest.raises(ValidationError, match="TERMII_TIMEOUT_SECONDS"):
        _settings(termii_timeout_seconds=9.0, termii_total_timeout_seconds=8.0)


def test_complete_production_config_with_termii_starts() -> None:
    settings = Settings(_env_file=None, **{**PRODUCTION, **TERMII})  # type: ignore[arg-type]
    assert settings.sms_provider == "termii"


def test_production_refuses_a_placeholder_termii_key() -> None:
    with pytest.raises(ValidationError, match="TERMII_API_KEY est une valeur d'exemple"):
        Settings(
            _env_file=None,
            **{**PRODUCTION, **TERMII, "termii_api_key": "change-me-termii"},  # type: ignore[arg-type]
        )


def test_console_stays_the_default_and_unchanged() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        jwt_secret="x" * 32,
    )
    assert settings.sms_provider == "console"
    assert type(get_sms_provider(settings)).__name__ == "ConsoleSmsProvider"


def test_termii_is_selected_by_sms_provider() -> None:
    assert isinstance(get_sms_provider(_settings()), TermiiSmsProvider)


# ---------------------------------------------------- requête exacte, canaux


async def test_sms_request_matches_termii_documentation() -> None:
    fake = FakeTermii()
    await fake.provider(_settings()).send_otp("+221771234567", "123456")

    (request,) = fake.requests
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}{TERMII_SEND_PATH}"
    body = fake.bodies[0]
    assert set(body) == {"api_key", "to", "from", "sms", "type", "channel"}
    assert body["api_key"] == API_KEY
    assert body["to"] == "221771234567"  # international, SANS « + »
    assert body["from"] == SENDER
    assert body["type"] == "plain"
    assert body["channel"] == "dnd"  # défaut OTP_SMS_CHANNEL
    assert "123456" in body["sms"] and "5 min" in body["sms"]  # OTP_TTL_SECONDS=300
    # La clé d'API ne voyage jamais dans l'URL.
    assert API_KEY not in str(request.url)


async def test_sms_route_is_configurable() -> None:
    fake = FakeTermii()
    await fake.provider(_settings(otp_sms_channel="generic")).send_otp("+221771234567", "123456")
    assert fake.bodies[0]["channel"] == "generic"


async def test_whatsapp_channel_sends_only_the_digits() -> None:
    fake = FakeTermii()
    settings = _settings(otp_channel="whatsapp", termii_whatsapp_sender="TerangaWA")
    await fake.provider(settings).send_otp("+221771234567", "123456")

    (body,) = fake.bodies
    assert (body["channel"], body["sms"], body["from"]) == ("whatsapp_otp", "123456", "TerangaWA")


async def test_conversational_whatsapp_channel_sends_the_message() -> None:
    fake = FakeTermii()
    settings = _settings(otp_channel="whatsapp", termii_whatsapp_channel="whatsapp")
    await fake.provider(settings).send_otp("+221771234567", "123456")

    (body,) = fake.bodies
    assert body["channel"] == "whatsapp" and "123456" in body["sms"]
    assert body["from"] == SENDER  # TERMII_WHATSAPP_SENDER absent : identifiant SMS


async def test_whatsapp_then_sms_falls_back_to_sms_when_whatsapp_fails() -> None:
    fake = FakeTermii(_response(400), httpx.Response(200, json=OK))
    await fake.provider(_settings(otp_channel="whatsapp_then_sms")).send_otp(
        "+221771234567", "123456"
    )
    assert [body["channel"] for body in fake.bodies] == ["whatsapp_otp", "dnd"]


async def test_whatsapp_then_sms_stops_when_whatsapp_succeeds() -> None:
    fake = FakeTermii()
    await fake.provider(_settings(otp_channel="whatsapp_then_sms")).send_otp(
        "+221771234567", "123456"
    )
    assert [body["channel"] for body in fake.bodies] == ["whatsapp_otp"]


# ------------------------------------------------- essais, échecs, budget


async def test_a_transient_failure_is_retried_once() -> None:
    fake = FakeTermii(_response(503), httpx.Response(200, json=OK))
    await fake.provider(_settings()).send_otp("+221771234567", "123456")
    assert len(fake.requests) == 2


async def test_a_network_failure_is_retried_then_reported() -> None:
    fake = FakeTermii(httpx.ConnectError("injoignable"))
    with pytest.raises(OtpEnvoiIndisponibleError) as exc:
        await fake.provider(_settings()).send_otp("+221771234567", "123456")
    assert len(fake.requests) == 2  # TERMII_MAX_ATTEMPTS
    assert (exc.value.status_code, exc.value.code) == (503, "OTP_ENVOI_INDISPONIBLE")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_a_request_error_is_never_retried(status: int) -> None:
    fake = FakeTermii(_response(status))
    with pytest.raises(OtpEnvoiIndisponibleError):
        await fake.provider(_settings()).send_otp("+221771234567", "123456")
    assert len(fake.requests) == 1


async def test_a_2xx_without_confirmation_is_not_a_success() -> None:
    fake = FakeTermii(
        httpx.Response(200, json={"message": "?"}), httpx.Response(200, text="<html>")
    )
    with pytest.raises(OtpEnvoiIndisponibleError):
        await fake.provider(_settings()).send_otp("+221771234567", "123456")


async def test_total_budget_is_enforced() -> None:
    """Un Termii qui ne répond jamais ne bloque pas la requête au-delà du
    budget total."""

    async def _hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=OK)

    settings = _settings(termii_timeout_seconds=0.05, termii_total_timeout_seconds=0.2)
    provider = TermiiSmsProvider(settings, transport=httpx.MockTransport(_hang))
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(OtpEnvoiIndisponibleError):
        await provider.send_otp("+221771234567", "123456")
    assert loop.time() - started < 1.0


async def test_logs_never_contain_the_key_the_code_or_the_full_number(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeTermii(_response(503), _response(401))
    with caplog.at_level(logging.DEBUG), pytest.raises(OtpEnvoiIndisponibleError):
        await fake.provider(_settings()).send_otp("+221771234567", "654321")
    assert caplog.text
    for secret in (API_KEY, "654321", "221771234567"):
        assert secret not in caplog.text
    assert mask_phone("+221771234567") in caplog.text


def test_mask_phone() -> None:
    assert mask_phone("+221771234567") == "+221*******67"


# --------------------------------------------------- routage (otp.request_otp)


def _routing_settings(phone: str) -> Settings:
    return _settings(otp_test_whitelist=[phone], otp_test_code=TEST_CODE)


async def test_a_whitelisted_number_keeps_the_test_code_and_never_reaches_termii(
    db_session: AsyncSession,
) -> None:
    listed = unique_phone()
    settings = _routing_settings(listed)
    fake = FakeTermii()

    await otp_service.request_otp(
        db_session, listed, settings=settings, sms_provider=fake.provider(settings)
    )

    assert fake.requests == []
    assert await otp_service.verify_otp(db_session, listed, TEST_CODE, settings=settings) == listed


async def test_any_other_number_gets_a_real_code_through_termii(db_session: AsyncSession) -> None:
    listed, other = unique_phone(), unique_phone()
    settings = _routing_settings(listed)
    fake = FakeTermii()

    await otp_service.request_otp(
        db_session, other, settings=settings, sms_provider=fake.provider(settings)
    )

    (body,) = fake.bodies
    assert body["to"] == other.removeprefix("+")
    match = re.search("[0-9]{" + str(settings.otp_code_length) + "}", body["sms"])
    assert match is not None
    sent_code = match.group()
    # Le code reçu par SMS est bien celui que NOUS vérifions (haché en base).
    assert await otp_service.verify_otp(db_session, other, sent_code, settings=settings) == other


# ---------------------------------------------------------- par l'API


@pytest.fixture
def termii_app(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., FakeTermii]]:
    settings = get_settings().model_copy(update=TERMII)

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _install(*script: httpx.Response | Exception) -> FakeTermii:
        fake = FakeTermii(*script)
        monkeypatch.setattr(otp_service, "get_sms_provider", lambda _s: fake.provider(settings))
        return fake

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_otp_rate_limiter] = lambda: limiter
    yield _install
    app.dependency_overrides.clear()


async def test_a_termii_outage_gets_a_503_the_browser_can_read(
    termii_app: Callable[..., FakeTermii],
) -> None:
    termii_app(_response(500))
    origin = get_settings().cors_origins[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            "/api/v1/auth/request-otp", json={"phone": unique_phone()}, headers={"Origin": origin}
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OTP_ENVOI_INDISPONIBLE"
    assert response.headers["access-control-allow-origin"] == origin


async def test_a_successful_delivery_keeps_the_non_enumerating_204(
    termii_app: Callable[..., FakeTermii],
) -> None:
    fake = termii_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/v1/auth/request-otp", json={"phone": unique_phone()})
    assert response.status_code == 204
    assert len(fake.requests) == 1
