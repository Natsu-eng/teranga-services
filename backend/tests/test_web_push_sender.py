"""Envoi Web Push réel par pywebpush (app/services/web_push.py).

Aucun réseau : un faux service de push (adaptateur `requests`) reçoit la
requête produite par pywebpush. Le navigateur abonné est simulé par une
vraie paire de clés : on DÉCHIFFRE le contenu reçu, comme le ferait
l'appareil, pour prouver ce qu'il contient (et ce qu'il ne contient pas).
"""

import json
import os
import uuid
from collections.abc import Callable

import http_ece
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

from app.core.config import Settings
from app.core.vapid import b64url_decode, b64url_encode, encode_public_key, generate_key_pair
from app.services.message_notifications import build_new_message_notification
from app.services.web_push import (
    PushOutcome,
    PushTarget,
    WebPushSender,
    is_allowed_push_endpoint,
    push_http_session,
)

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abonnement-de-test"
SUBJECT = "mailto:contact@teranga.example"
CONVERSATION_ID = uuid.uuid4()
NOTIFICATION = build_new_message_notification(CONVERSATION_ID)


class FakeBrowser:
    """Clés d'un navigateur abonné (p256dh + secret d'authentification)."""

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.auth_secret = os.urandom(16)

    def target(self, endpoint: str = ENDPOINT) -> PushTarget:
        return PushTarget(
            endpoint=endpoint,
            p256dh=encode_public_key(self.private_key.public_key()),
            auth=b64url_encode(self.auth_secret),
        )

    def decrypt(self, body: bytes) -> dict[str, object]:
        plain = http_ece.decrypt(
            body,
            private_key=self.private_key,
            auth_secret=self.auth_secret,
            version="aes128gcm",
        )
        decoded: dict[str, object] = json.loads(plain)
        return decoded


class FakePushService(BaseAdapter):
    """Répond selon le scénario ; enregistre chaque requête reçue."""

    def __init__(
        self,
        status: int = 201,
        headers: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.status, self.headers, self.error = status, headers or {}, error
        self.requests: list[requests.PreparedRequest] = []

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:  # type: ignore[override]
        self.requests.append(request)
        if self.error:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response.headers = CaseInsensitiveDict(self.headers)
        response._content = b'{"reason": "detail libre du service"}'
        response.url = request.url or ""
        response.request = request
        return response

    def close(self) -> None:
        return None

    def session_factory(self) -> Callable[[], requests.Session]:
        def factory() -> requests.Session:
            session = push_http_session()  # la VRAIE session (redirections refusées)
            session.mount("https://", self)
            return session

        return factory


def _settings(**overrides: object) -> Settings:
    public_key, private_key = generate_key_pair()
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        "web_push_enabled": True,
        "vapid_public_key": public_key,
        "vapid_private_key": private_key,
        "vapid_subject": SUBJECT,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def _sender(service: FakePushService, settings: Settings | None = None) -> WebPushSender:
    return WebPushSender(settings or _settings(), session_factory=service.session_factory())


# ------------------------------------------------------------ requête


async def test_request_is_encrypted_signed_and_sober() -> None:
    settings = _settings(web_push_ttl_seconds=3600)
    browser, service = FakeBrowser(), FakePushService()

    result = await _sender(service, settings).send(browser.target(), NOTIFICATION)

    assert result.outcome is PushOutcome.DELIVERED
    (request,) = service.requests
    assert request.method == "POST" and request.url == ENDPOINT
    headers = request.headers
    assert headers["Content-Encoding"] == "aes128gcm"
    assert headers["TTL"] == "3600"
    assert headers["Urgency"] == "high"
    assert headers["Topic"] == CONVERSATION_ID.hex
    # Jeton VAPID : signé par NOTRE clé (sa clé publique voyage dans `k=`).
    authorization = str(headers["Authorization"])
    assert authorization.startswith("vapid t=")
    assert f"k={settings.vapid_public_key}" in authorization
    assert settings.vapid_private_key and settings.vapid_private_key not in str(headers)

    # Le contenu chiffré ne se lit qu'avec les clés du navigateur abonné.
    assert isinstance(request.body, bytes)
    assert b"Nouveau message" not in request.body
    assert browser.decrypt(request.body) == {
        "title": "Téranga",
        "body": "Nouveau message sur Téranga",
        "url": f"/messages/{CONVERSATION_ID}",
        "tag": f"conversation-{CONVERSATION_ID}",
    }


async def test_another_browser_cannot_read_the_content() -> None:
    browser, intruder, service = FakeBrowser(), FakeBrowser(), FakePushService()
    await _sender(service).send(browser.target(), NOTIFICATION)
    body = service.requests[0].body
    assert isinstance(body, bytes)
    with pytest.raises(Exception):  # noqa: B017 -- toute erreur de déchiffrement convient
        intruder.decrypt(body)


# ------------------------------------------------------------ résultats


@pytest.mark.parametrize("status", [404, 410])
async def test_a_dead_subscription_is_reported_gone(status: int) -> None:
    service = FakePushService(status=status)
    result = await _sender(service).send(FakeBrowser().target(), NOTIFICATION)
    assert result.outcome is PushOutcome.GONE
    assert result.detail == f"HTTP {status}"


@pytest.mark.parametrize("status", [400, 403, 413, 429, 500, 503])
async def test_other_refusals_fail_without_the_service_message(status: int) -> None:
    service = FakePushService(status=status)
    result = await _sender(service).send(FakeBrowser().target(), NOTIFICATION)
    assert result.outcome is PushOutcome.FAILED
    assert result.detail == f"HTTP {status}"
    assert "detail libre" not in result.detail


@pytest.mark.parametrize(
    "error", [requests.ConnectionError("injoignable"), requests.Timeout("trop lent")]
)
async def test_network_errors_fail_with_their_type_only(error: Exception) -> None:
    service = FakePushService(error=error)
    result = await _sender(service).send(FakeBrowser().target(), NOTIFICATION)
    assert result.outcome is PushOutcome.FAILED
    assert result.detail == type(error).__name__


async def test_a_redirect_is_never_followed() -> None:
    service = FakePushService(status=307, headers={"Location": "http://169.254.169.254/latest"})
    result = await _sender(service).send(FakeBrowser().target(), NOTIFICATION)
    assert result.outcome is PushOutcome.FAILED
    assert result.detail == "TooManyRedirects"
    assert len(service.requests) == 1  # aucune requête vers la cible de la redirection


async def test_a_no_longer_allowed_host_gets_no_request() -> None:
    service = FakePushService()
    target = FakeBrowser().target("https://interne.teranga.example/push")
    result = await _sender(service).send(target, NOTIFICATION)
    assert result.outcome is PushOutcome.FAILED
    assert service.requests == []


# ------------------------------------------------------- hôtes autorisés

ALLOWED = [
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QJx",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
        "https://fcm.googleapis.com:443/fcm/send/abc",
    ],
)
def test_real_push_services_are_allowed(endpoint: str) -> None:
    assert is_allowed_push_endpoint(endpoint, ALLOWED)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # pas https
        "https://evilfcm.googleapis.com.attaquant.example/x",  # suffixe trompeur
        "https://fcm.googleapis.com.attaquant.example/x",
        "https://attaquant.example/fcm.googleapis.com",
        "https://localhost/push",
        "https://169.254.169.254/latest/meta-data",
        "https://user:pass@fcm.googleapis.com/x",  # identifiants
        "https://fcm.googleapis.com:8443/x",  # autre port
        "https://fcm.googleapis.com/x y",  # blanc
        "pas une url",
    ],
)
def test_anything_else_is_refused(endpoint: str) -> None:
    assert not is_allowed_push_endpoint(endpoint, ALLOWED)


def test_the_sender_refuses_to_start_without_push_enabled() -> None:
    disabled = _settings().model_copy(update={"web_push_enabled": False})
    with pytest.raises(ValueError, match="Web Push incomplet"):
        WebPushSender(disabled)


def test_vapid_key_from_settings_round_trips() -> None:
    settings = _settings()
    assert settings.vapid_private_key is not None
    assert len(b64url_decode(settings.vapid_private_key)) == 32
