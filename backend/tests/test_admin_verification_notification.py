"""Notification e-mail des admins quand un artisan COMPLÈTE son dossier de
vérification (app/services/admin_notifications.py, app/services/email.py).

Prouvé ici, sans réseau (fournisseur enregistreur, faux serveur SMTP) :
- un e-mail par passage à « dossier complet en attente » -- jamais pour un
  dossier partiel, jamais un par document, jamais une seconde fois ;
- un échec d'e-mail n'interrompt jamais l'envoi de l'artisan ;
- aucun secret ni donnée sensible : pas de document, pas de numéro, pas le
  mot de passe SMTP ;
- configuration SMTP refusée au démarrage si incomplète (liste complète).
"""

import logging
import smtplib
from collections.abc import AsyncGenerator, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile, Verification
from app.models.enums import Role, VerificationDocType, VerificationStatus
from app.models.user import User
from app.services import admin_notifications
from app.services.admin_notifications import (
    ADMIN_VERIFICATIONS_PATH,
    VERIFICATION_SUBJECT,
    build_verification_submitted_email,
)
from app.services.email import OutgoingEmail, SmtpEmailProvider, get_email_provider
from app.services.rate_limit import SlidingWindowRateLimiter, get_document_upload_rate_limiter
from app.services.verification import is_awaiting_review
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png

ADMINS = ["admin@teranga.example", "equipe@teranga.example"]
SMTP_PASSWORD = "mot-de-passe-smtp-de-test"
FRONT = "https://beta.teranga.example"


class RecordingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[OutgoingEmail] = []
        self.error = error

    async def send(self, email: OutgoingEmail) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(email)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


# --------------------------------------------------- règle de déclenchement


def _verification(doc_type: VerificationDocType, status: VerificationStatus) -> Verification:
    return Verification(doc_type=doc_type, status=status, doc_url="x")


CNI, SELFIE = VerificationDocType.CNI, VerificationDocType.SELFIE
PENDING, APPROVED, REJECTED = (
    VerificationStatus.PENDING,
    VerificationStatus.APPROVED,
    VerificationStatus.REJECTED,
)


@pytest.mark.parametrize(
    ("documents", "expected"),
    [
        ([], False),  # rien envoyé
        ([(CNI, PENDING)], False),  # dossier PARTIEL : pas encore de notification
        ([(CNI, PENDING), (SELFIE, PENDING)], True),  # complet, en attente
        ([(CNI, APPROVED), (SELFIE, PENDING)], True),  # reste un document à examiner
        ([(CNI, APPROVED), (SELFIE, APPROVED)], False),  # déjà vérifié
        ([(CNI, REJECTED), (SELFIE, PENDING)], False),  # un refus attend un renvoi
    ],
)
def test_awaiting_review_means_a_complete_dossier_with_something_to_review(
    documents: list[tuple[VerificationDocType, VerificationStatus]], expected: bool
) -> None:
    verifications = [_verification(doc_type, status) for doc_type, status in documents]
    assert is_awaiting_review(verifications, [CNI, SELFIE]) is expected


# ----------------------------------------------------- parcours par l'API


@pytest.fixture
def notifying_app(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[RecordingProvider]:
    settings = get_settings().model_copy(
        update={
            "storage_local_dir": str(tmp_path),
            "admin_notification_emails": ADMINS,
            "frontend_public_base_url": FRONT,
            "verification_required_doc_types": [CNI, SELFIE],
        }
    )
    provider = RecordingProvider()
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_document_upload_rate_limiter] = lambda: limiter
    yield provider
    app.dependency_overrides.clear()


async def _upload(user: User, doc_type: str) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.post(
            "/api/v1/artisans/me/documents",
            headers={"Authorization": f"Bearer {encode_access_token(user)}"},
            data={"doc_type": doc_type},
            files={"file": ("doc.png", make_png(), "image/png")},
        )


async def _artisan(db_session: AsyncSession, full_name: str = "Idrissa Fall") -> User:
    user = await make_user(db_session, role=Role.ARTISAN, full_name=full_name)
    await make_artisan_profile(db_session, user=user)
    return user


async def test_one_email_when_the_dossier_becomes_complete_and_never_again(
    db_session: AsyncSession, notifying_app: RecordingProvider
) -> None:
    artisan = await _artisan(db_session)

    first = await _upload(artisan, "cni")
    assert first.status_code == 201
    assert notifying_app.sent == []  # dossier partiel : rien

    second = await _upload(artisan, "selfie")
    assert second.status_code == 201
    assert len(notifying_app.sent) == 1  # dossier complet : UN e-mail

    # Renvoi d'un document alors que le dossier attend déjà : pas de relance.
    again = await _upload(artisan, "cni")
    assert again.status_code == 201
    assert len(notifying_app.sent) == 1


async def test_a_resubmission_after_a_rejection_notifies_again(
    db_session: AsyncSession, notifying_app: RecordingProvider
) -> None:
    artisan = await _artisan(db_session)
    await _upload(artisan, "cni")
    await _upload(artisan, "selfie")
    assert len(notifying_app.sent) == 1

    # L'admin refuse le selfie : le dossier n'attend plus rien...
    documents = (
        (
            await db_session.execute(
                select(Verification)
                .join(ArtisanProfile, ArtisanProfile.id == Verification.artisan_id)
                .where(ArtisanProfile.user_id == artisan.id)
            )
        )
        .scalars()
        .all()
    )
    assert {v.doc_type for v in documents} == {CNI, SELFIE}
    selfie = next(v for v in documents if v.doc_type == SELFIE)
    selfie.status = REJECTED
    # Envois antérieurs datés dans le passé : dans la transaction unique du
    # test, now() renverrait la même date pour le renvoi (en production,
    # chaque envoi est une requête -- donc une transaction -- distincte).
    for document in documents:
        document.created_at = document.created_at - timedelta(minutes=5)
    await db_session.flush()

    # ... et le renvoi du selfie est un NOUVEAU passage en attente.
    await _upload(artisan, "selfie")
    assert len(notifying_app.sent) == 2


async def test_the_email_is_sober_and_leaks_nothing(
    db_session: AsyncSession, notifying_app: RecordingProvider
) -> None:
    artisan = await _artisan(db_session, full_name="Awa Ndiaye")
    await _upload(artisan, "cni")
    await _upload(artisan, "selfie")

    (email,) = notifying_app.sent
    assert email.to == tuple(ADMINS)
    assert email.subject == VERIFICATION_SUBJECT
    assert "Un artisan a soumis ses documents de vérification sur Téranga." in email.body
    assert f"{FRONT}{ADMIN_VERIFICATIONS_PATH}" in email.body
    assert "Artisan : Awa Ndiaye" in email.body
    # Ni numéro, ni chemin de document, ni identifiant interne.
    assert artisan.phone not in email.body
    assert "verification-documents" not in email.body and ".png" not in email.body
    assert str(artisan.id) not in email.body


async def test_an_email_failure_never_breaks_the_upload(
    db_session: AsyncSession,
    notifying_app: RecordingProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    notifying_app.error = ConnectionRefusedError(f"refusé : {SMTP_PASSWORD}")
    artisan = await _artisan(db_session)

    with caplog.at_level(logging.INFO):
        await _upload(artisan, "cni")
        response = await _upload(artisan, "selfie")

    assert response.status_code == 201  # l'envoi de l'artisan est réussi
    stored = (
        (
            await db_session.execute(
                select(Verification.doc_type)
                .join(ArtisanProfile, ArtisanProfile.id == Verification.artisan_id)
                .where(ArtisanProfile.user_id == artisan.id)
            )
        )
        .scalars()
        .all()
    )
    assert set(stored) == {CNI, SELFIE}
    assert "NON envoyée : ConnectionRefusedError" in caplog.text
    assert SMTP_PASSWORD not in caplog.text  # le message de l'erreur n'est pas recopié


async def test_no_recipient_configured_means_no_email(
    db_session: AsyncSession, notifying_app: RecordingProvider
) -> None:
    settings = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"admin_notification_emails": []}
    )
    artisan = await _artisan(db_session)
    await _upload(artisan, "cni")
    response = await _upload(artisan, "selfie")

    assert response.status_code == 201
    assert notifying_app.sent == []


# ------------------------------------------------------------- contenu


@pytest.mark.parametrize("name", ["+221 77 123 45 67", "221771234567", "", None])
def test_a_phone_like_or_empty_name_is_never_sent(name: str | None) -> None:
    email = build_verification_submitted_email(
        name, _settings(admin_notification_emails=ADMINS, frontend_public_base_url=FRONT)
    )
    assert "Artisan :" not in email.body


def test_a_name_cannot_inject_lines() -> None:
    email = build_verification_submitted_email(
        "Awa\nBcc: pirate@example.com", _settings(admin_notification_emails=ADMINS)
    )
    assert "Artisan : Awa Bcc: pirate@example.com" in email.body
    assert email.subject == VERIFICATION_SUBJECT  # le sujet ne contient jamais le nom


# ------------------------------------------------------- configuration


def test_console_is_the_default_and_sends_nothing() -> None:
    settings = _settings()
    assert settings.email_provider == "console"
    assert type(get_email_provider(settings)).__name__ == "ConsoleEmailProvider"


def test_smtp_requires_its_settings_listed_at_once_without_the_password() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(email_provider="smtp", smtp_password=SMTP_PASSWORD)
    message = str(exc.value)
    assert "E-mail SMTP incomplet, à renseigner : SMTP_HOST, SMTP_USER, EMAIL_FROM." in message
    assert "ADMIN_NOTIFICATION_EMAILS est vide" in message
    assert SMTP_PASSWORD not in message


def test_addresses_are_checked_and_pasted_values_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ADMIN_NOTIFICATION_EMAILS", " admin@teranga.example ,\n equipe@teranga.example\n"
    )
    assert _settings().admin_notification_emails == ADMINS
    with pytest.raises(ValidationError, match="n'est pas une adresse e-mail"):
        _settings(admin_notification_emails=["pas-une-adresse"])


SMTP_SETTINGS: dict[str, object] = {
    "email_provider": "smtp",
    "smtp_host": "smtp.example.com",
    "smtp_user": "notifications@teranga.example",
    "smtp_password": SMTP_PASSWORD,
    "email_from": "notifications@teranga.example",
    "admin_notification_emails": ADMINS,
}


def test_complete_smtp_configuration_selects_the_smtp_provider() -> None:
    assert isinstance(get_email_provider(_settings(**SMTP_SETTINGS)), SmtpEmailProvider)


# ------------------------------------------------------------ transport


class FakeSmtp:
    """Faux serveur SMTP : enregistre chaque appel, n'ouvre aucune connexion."""

    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, timeout: float, **kwargs: Any) -> None:
        self.calls: list[tuple[str, Any]] = [("connect", (host, port, timeout))]
        self.kwargs = kwargs
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append(("quit", None))

    def starttls(self, context: Any) -> None:
        self.calls.append(("starttls", context))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", (user, password)))

    def send_message(self, message: Any) -> None:
        self.calls.append(("send", message))


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    # Le module email.py appelle smtplib.SMTP / SMTP_SSL au moment de l'envoi.
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    return FakeSmtp


async def test_smtp_uses_starttls_before_login_and_sends_a_plain_message(
    fake_smtp: type[FakeSmtp],
) -> None:
    provider = SmtpEmailProvider(_settings(**SMTP_SETTINGS))
    await provider.send(OutgoingEmail(to=tuple(ADMINS), subject="Sujet", body="Corps"))

    (server,) = fake_smtp.instances
    steps = [name for name, _ in server.calls]
    assert steps == ["connect", "starttls", "login", "send", "quit"]
    assert server.calls[0][1] == ("smtp.example.com", 587, 10.0)
    message = server.calls[3][1]
    assert message["From"] == "notifications@teranga.example"
    assert message["To"] == ", ".join(ADMINS)
    assert message["Subject"] == "Sujet"
    assert not message.is_multipart()  # aucune pièce jointe


async def test_smtp_ssl_mode_uses_implicit_tls(fake_smtp: type[FakeSmtp]) -> None:
    provider = SmtpEmailProvider(_settings(**SMTP_SETTINGS, smtp_port=465, smtp_security="ssl"))
    await provider.send(OutgoingEmail(to=tuple(ADMINS), subject="Sujet", body="Corps"))

    (server,) = fake_smtp.instances
    assert [name for name, _ in server.calls] == ["connect", "login", "send", "quit"]
    assert "context" in server.kwargs  # certificat du serveur vérifié
