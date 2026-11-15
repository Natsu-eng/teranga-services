"""Envoi d'e-mails, derrière une interface indépendante du fournisseur (même
principe que `app.services.sms`).

Le fournisseur actif est choisi par configuration (`EMAIL_PROVIDER`) :

- `console` (défaut, dev/test) : rien n'est envoyé, l'e-mail est seulement
  journalisé (destinataires et sujet ; le corps seulement en development/
  test) ;
- `smtp` : envoi réel par un serveur SMTP (`SMTP_*`, ex. Gmail : port 587 +
  STARTTLS et mot de passe d'application). `smtplib` (bibliothèque standard,
  aucune dépendance ajoutée) est synchrone : l'envoi part dans un thread, la
  boucle asynchrone n'est jamais bloquée, et le délai est borné
  (`SMTP_TIMEOUT_SECONDS`).

Jamais de secret dans les journaux : ni le mot de passe SMTP, ni le corps
d'un message hors poste de développement.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    """Un e-mail texte brut (aucune pièce jointe, aucun HTML)."""

    to: tuple[str, ...]
    subject: str
    body: str


class EmailProvider(Protocol):
    async def send(self, email: OutgoingEmail) -> None:
        """Envoie l'e-mail ; lève une exception en cas d'échec."""
        ...


class ConsoleEmailProvider:
    """Fournisseur de dev : n'envoie rien, journalise l'e-mail."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, email: OutgoingEmail) -> None:
        if self._settings.is_local:
            logger.info(
                "[dev] E-mail non envoyé (EMAIL_PROVIDER=console) à %s : %s\n%s",
                ", ".join(email.to),
                email.subject,
                email.body,
            )
        else:
            logger.warning(
                "EMAIL_PROVIDER=console hors poste de développement (ENVIRONMENT=%s) : "
                "e-mail « %s » NON envoyé.",
                self._settings.environment,
                email.subject,
            )


class SmtpEmailProvider:
    """Envoi réel par SMTP (STARTTLS sur 587, ou SSL implicite sur 465).

    Le certificat du serveur est TOUJOURS vérifié (contexte TLS par défaut) :
    jamais d'identifiants envoyés à un serveur non authentifié.
    """

    def __init__(self, settings: Settings) -> None:
        host, user, password, sender = (
            settings.smtp_host,
            settings.smtp_user,
            settings.smtp_password,
            settings.email_from,
        )
        # Défense en profondeur : déjà exigés au démarrage (validate_email_settings).
        if not (host and user and password and sender):
            raise ValueError(
                "SMTP incomplet : voir SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM."
            )
        self._host = host
        self._port = settings.smtp_port
        self._security = settings.smtp_security
        self._user = user
        self._password = password
        self._sender = sender
        self._timeout = settings.smtp_timeout_seconds

    def _build(self, email: OutgoingEmail) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = ", ".join(email.to)
        message["Subject"] = email.subject
        message.set_content(email.body)
        return message

    def _send_blocking(self, email: OutgoingEmail) -> None:
        message = self._build(email)
        context = ssl.create_default_context()
        if self._security == "ssl":
            with smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout, context=context
            ) as server:
                server.login(self._user, self._password)
                server.send_message(message)
            return
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
            server.starttls(context=context)
            server.login(self._user, self._password)
            server.send_message(message)

    async def send(self, email: OutgoingEmail) -> None:
        await asyncio.to_thread(self._send_blocking, email)


def get_email_provider(settings: Settings | None = None) -> EmailProvider:
    settings = settings or get_settings()
    if settings.email_provider == "smtp":
        return SmtpEmailProvider(settings)
    return ConsoleEmailProvider(settings)
