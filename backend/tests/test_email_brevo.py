"""Fournisseur e-mail Brevo (API HTTP, port 443) -- app/services/email.py.

Render bloque le SMTP sortant : Brevo est la voie d'envoi réelle en beta.
Aucun réseau : un faux serveur Brevo (`httpx.MockTransport`) enregistre la
requête et répond selon le scénario.
"""

import json
import logging
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role, VerificationDocType
from app.services import admin_notifications
from app.services.admin_notifications import notify_verification_submitted
from app.services.email import (
    BREVO_SEND_PATH,
    BrevoEmailProvider,
    EmailSendError,
    OutgoingEmail,
    get_email_provider,
    html_from_text,
)
from app.services.rate_limit import SlidingWindowRateLimiter, get_document_upload_rate_limiter
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png
from tests.test_production_settings import PRODUCTION
from tests.test_termii import TERMII

API_KEY = "xkeysib-cle-de-test-0123456789abcdef"
SENDER = "notifications@teranga.example"
ADMINS = ["admin@teranga.example"]
BREVO: dict[str, object] = {
    "email_provider": "brevo",
    "brevo_api_key": API_KEY,
    "email_from": SENDER,
    "admin_notification_emails": ADMINS,
}
EMAIL = OutgoingEmail(to=tuple(ADMINS), subject="Sujet", body="Bonjour,\n\nLigne 1\nLigne 2")


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        **BREVO,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


class FakeBrevo:
    def __init__(self, response: httpx.Response | Exception | None = None) -> None:
        self.response = response or httpx.Response(201, json={"messageId": "<1@relay>"})
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def provider(self, settings: Settings | None = None) -> BrevoEmailProvider:
        return BrevoEmailProvider(
            settings or _settings(), transport=httpx.MockTransport(self.handler)
        )


# ------------------------------------------------------------ requête


async def test_request_matches_brevo_documentation() -> None:
    fake = FakeBrevo()
    await fake.provider().send(EMAIL)

    (request,) = fake.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.brevo.com/v3{BREVO_SEND_PATH}"
    assert request.headers["api-key"] == API_KEY
    assert API_KEY not in str(request.url)  # la clé ne voyage que dans l'en-tête
    body = json.loads(request.content)
    assert body == {
        "sender": {"email": SENDER},
        "to": [{"email": "admin@teranga.example"}],
        "subject": "Sujet",
        "textContent": "Bonjour,\n\nLigne 1\nLigne 2",
        "htmlContent": "<p>Bonjour,</p><p>Ligne 1<br>Ligne 2</p>",
    }


def test_html_version_escapes_every_value() -> None:
    assert html_from_text("Artisan : <script>x</script> & co") == (
        "<p>Artisan : &lt;script&gt;x&lt;/script&gt; &amp; co</p>"
    )


@pytest.mark.parametrize("status", [201, 202])
async def test_201_and_202_are_successes(status: int) -> None:
    await FakeBrevo(httpx.Response(status, json={})).provider().send(EMAIL)


@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "invalid_parameter"), (401, "unauthorized"), (403, "permission_denied")],
)
async def test_a_refusal_raises_a_safe_error_without_the_provider_message(
    status: int, code: str
) -> None:
    fake = FakeBrevo(
        httpx.Response(status, json={"code": code, "message": "sender admin@teranga.example ..."})
    )
    with pytest.raises(EmailSendError) as exc:
        await fake.provider().send(EMAIL)
    assert exc.value.safe_detail == f"Brevo HTTP {status} ({code})"
    assert "admin@teranga.example" not in str(exc.value)


async def test_a_non_json_error_is_still_reported_safely() -> None:
    with pytest.raises(EmailSendError, match=r"Brevo HTTP 502 \(réponse non JSON\)"):
        await FakeBrevo(httpx.Response(502, text="<html>")).provider().send(EMAIL)


# ------------------------------------------------------- best-effort


async def test_a_brevo_refusal_never_escapes_the_notification(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeBrevo(httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"}))
    with caplog.at_level(logging.INFO):
        await notify_verification_submitted(
            "Awa Ndiaye", _settings(), provider=fake.provider()
        )  # ne lève rien
    assert "NON envoyée : Brevo HTTP 401 (unauthorized)." in caplog.text
    assert API_KEY not in caplog.text
    assert "Key not found" not in caplog.text


async def test_a_network_failure_never_escapes_the_notification(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeBrevo(httpx.ConnectError("injoignable"))
    with caplog.at_level(logging.INFO):
        await notify_verification_submitted("Awa Ndiaye", _settings(), provider=fake.provider())
    assert "NON envoyée : ConnectError." in caplog.text


@pytest.fixture
def brevo_app(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeBrevo]:
    settings = get_settings().model_copy(
        update={
            **BREVO,
            "storage_local_dir": str(tmp_path),
            "verification_required_doc_types": [
                VerificationDocType.CNI,
                VerificationDocType.SELFIE,
            ],
        }
    )
    fake = FakeBrevo(httpx.Response(500, json={"code": "internal_error"}))
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda s: fake.provider(s))

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_document_upload_rate_limiter] = lambda: limiter
    yield fake
    app.dependency_overrides.clear()


async def test_the_artisan_upload_succeeds_even_when_brevo_fails(
    db_session: AsyncSession, brevo_app: FakeBrevo
) -> None:
    artisan = await make_user(db_session, role=Role.ARTISAN, full_name="Idrissa Fall")
    await make_artisan_profile(db_session, user=artisan)
    headers = {"Authorization": f"Bearer {encode_access_token(artisan)}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        statuses = [
            (
                await http.post(
                    "/api/v1/artisans/me/documents",
                    headers=headers,
                    data={"doc_type": doc_type},
                    files={"file": ("doc.png", make_png(), "image/png")},
                )
            ).status_code
            for doc_type in ("cni", "selfie")
        ]

    assert statuses == [201, 201]
    # Déclenchement inchangé : un seul appel, au dossier complet.
    assert len(brevo_app.requests) == 1


# ------------------------------------------------------- configuration


def test_brevo_is_selected_by_email_provider() -> None:
    assert isinstance(get_email_provider(_settings()), BrevoEmailProvider)


def test_brevo_requires_its_settings_listed_at_once_without_the_key() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(brevo_api_key=None, email_from=None, admin_notification_emails=[])
    message = str(exc.value)
    assert "E-mail Brevo incomplet, à renseigner : BREVO_API_KEY, EMAIL_FROM." in message
    assert "avec EMAIL_PROVIDER=brevo, au moins un destinataire" in message


def test_a_pasted_key_is_cleaned_and_a_broken_one_refused_without_being_shown() -> None:
    assert _settings(brevo_api_key=f" {API_KEY}\r\n").brevo_api_key == API_KEY
    with pytest.raises(ValidationError) as exc:
        _settings(brevo_api_key="cle avec espace-0123456789")
    assert "BREVO_API_KEY contient un espace" in str(exc.value)
    assert "cle avec espace" not in str(exc.value)


def test_base_url_must_be_https() -> None:
    with pytest.raises(ValidationError, match="BREVO_API_BASE_URL invalide"):
        _settings(brevo_api_base_url="http://api.brevo.com/v3")


def test_production_accepts_brevo_and_refuses_a_placeholder_key() -> None:
    production = {**PRODUCTION, **TERMII, **BREVO}
    assert Settings(_env_file=None, **production).email_provider == "brevo"  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="BREVO_API_KEY est une valeur d'exemple"):
        Settings(_env_file=None, **{**production, "brevo_api_key": "change-me-brevo"})  # type: ignore[arg-type]


def test_console_stays_the_default() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        jwt_secret="x" * 32,
    )
    assert settings.email_provider == "console"
