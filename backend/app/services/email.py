"""Envoi d'e-mails, derrière une interface indépendante du fournisseur (même
principe que `app.services.sms`).

Le fournisseur actif est choisi par configuration (`EMAIL_PROVIDER`) :

- `console` (défaut, dev/test) : rien n'est envoyé, l'e-mail est seulement
  journalisé (destinataires et sujet ; le corps seulement en development/
  test) ;
- `brevo` : envoi réel par l'API HTTP transactionnelle de Brevo
  (`POST {BREVO_API_BASE_URL}/smtp/email`, en-tête `api-key`), sur le port
  443 -- la voie à utiliser sur Render, qui bloque le SMTP sortant ;
- `smtp` : envoi réel par un serveur SMTP (`SMTP_*`, ex. Gmail : port 587 +
  STARTTLS et mot de passe d'application). `smtplib` (bibliothèque standard,
  aucune dépendance ajoutée) est synchrone : l'envoi part dans un thread, la
  boucle asynchrone n'est jamais bloquée, et le délai est borné
  (`SMTP_TIMEOUT_SECONDS`). INUTILISABLE sur Render (ports SMTP bloqués :
  « OSError: Network is unreachable »).

Jamais de secret dans les journaux : ni le mot de passe SMTP, ni le corps
d'un message hors poste de développement.
"""

import asyncio
import html
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    """Un e-mail texte brut (aucune pièce jointe, aucun HTML)."""

    to: tuple[str, ...]
    subject: str
    body: str


class EmailSendError(Exception):
    """Refus du fournisseur (réponse HTTP en erreur). `safe_detail` (statut,
    code d'erreur du fournisseur) peut être journalisé : jamais la clé, ni
    le message libre du fournisseur (qui peut citer des adresses)."""

    def __init__(self, safe_detail: str) -> None:
        super().__init__(safe_detail)
        self.safe_detail = safe_detail


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


BREVO_SEND_PATH = "/smtp/email"


def html_from_text(text: str) -> str:
    """Version HTML du corps texte (Brevo exige `htmlContent` sans modèle) :
    texte ÉCHAPPÉ, un paragraphe par bloc, retours à la ligne conservés --
    aucune balise ne peut venir d'une donnée (nom de l'artisan compris)."""
    paragraphs = [block for block in text.split("\n\n") if block.strip()]
    return "".join(
        "<p>" + html.escape(block).replace("\n", "<br>") + "</p>" for block in paragraphs
    )


class BrevoEmailProvider:
    """Envoi réel par l'API HTTP transactionnelle de Brevo (port 443).

    Requête (documentation Brevo, « Send a transactional email ») :
    `POST {BREVO_API_BASE_URL}/smtp/email`, en-tête `api-key`, corps
    `{sender, to, subject, textContent, htmlContent}` ; succès = 201 (202
    pour un envoi planifié). L'expéditeur (`EMAIL_FROM`) doit être validé
    dans le compte Brevo.
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        api_key, sender = settings.brevo_api_key, settings.email_from
        # Défense en profondeur : déjà exigés au démarrage (validate_email_settings).
        if not (api_key and sender):
            raise ValueError("Brevo incomplet : voir BREVO_API_KEY et EMAIL_FROM.")
        self._api_key = api_key
        self._sender = sender
        self._base_url = settings.brevo_api_base_url
        self._timeout = settings.brevo_timeout_seconds
        # Point d'injection des tests (faux serveur Brevo, aucun réseau).
        self._transport = transport

    async def send(self, email: OutgoingEmail) -> None:
        payload = {
            "sender": {"email": self._sender},
            "to": [{"email": address} for address in email.to],
            "subject": email.subject,
            "textContent": email.body,
            "htmlContent": html_from_text(email.body),
        }
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        ) as client:
            # La clé voyage dans un EN-TÊTE, jamais dans l'URL (ni donc dans
            # les journaux de requêtes d'httpx).
            response = await client.post(
                BREVO_SEND_PATH,
                json=payload,
                headers={"api-key": self._api_key, "accept": "application/json"},
            )
        if response.status_code in (201, 202):
            return
        raise EmailSendError(f"Brevo HTTP {response.status_code} ({_brevo_error_code(response)})")


def _brevo_error_code(response: httpx.Response) -> str:
    """Code d'erreur Brevo (« unauthorized », « invalid_parameter »...) ;
    jamais le message libre, qui peut citer des adresses."""
    try:
        body = response.json()
    except ValueError:
        return "réponse non JSON"
    code = body.get("code") if isinstance(body, dict) else None
    return code if isinstance(code, str) else "code inconnu"


def get_email_provider(settings: Settings | None = None) -> EmailProvider:
    settings = settings or get_settings()
    if settings.email_provider == "brevo":
        return BrevoEmailProvider(settings)
    if settings.email_provider == "smtp":
        return SmtpEmailProvider(settings)
    return ConsoleEmailProvider(settings)
