"""Livraison des codes OTP par l'API Termii (SMS_PROVIDER=termii).

Termii n'est qu'un CANAL DE LIVRAISON : le code est généré, haché, limité
en tentatives et en débit, et vérifié par nous (app/services/otp.py). Les
numéros de OTP_TEST_WHITELIST (staging) n'arrivent jamais ici : ils gardent
le code de test.

API (documentation Termii, Messaging API et Send WhatsApp Token) :
`POST {TERMII_BASE_URL}/api/sms/send`, corps JSON
`{api_key, to, from, sms, type: "plain", channel}` ; numéro au format
international SANS « + » ; succès = HTTP 2xx et `"code": "ok"`.

Robustesse :
- délai par appel (TERMII_TIMEOUT_SECONDS) et budget TOTAL
  (TERMII_TOTAL_TIMEOUT_SECONDS), sous le délai du front ;
- nouvel essai (TERMII_MAX_ATTEMPTS) seulement sur panne TRANSITOIRE
  (réseau, délai, HTTP 429/5xx) ; une erreur de requête (4xx : clé,
  expéditeur, numéro) n'est jamais répétée ;
- OTP_CHANNEL=whatsapp_then_sms : WhatsApp d'abord, SMS si WhatsApp échoue ;
- échec final : `OtpEnvoiIndisponibleError` (503 applicative, en-têtes
  CORS conservés, message lisible), jamais une exception brute.

Sécurité des journaux : jamais la clé d'API, jamais le code, jamais le
corps de réponse brut ; le numéro est masqué (`+221*******67`).
"""

import asyncio
import logging
import math
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.services.sms import OtpEnvoiIndisponibleError

logger = logging.getLogger(__name__)

TERMII_SEND_PATH = "/api/sms/send"
# Format du message : `plain` (texte, alphabet GSM : les accents français
# courants y figurent).
TERMII_MESSAGE_TYPE = "plain"
# Statuts HTTP qui justifient un nouvel essai (surcharge, panne passagère).
_TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
# Pause entre deux essais (bornée de toute façon par le budget total).
_RETRY_PAUSE_SECONDS = 0.3
# Texte du SMS. Le code n'apparaît qu'ici, jamais dans un journal.
_SMS_TEMPLATE = (
    "Téranga : votre code de connexion est {code}. Il expire dans {minutes} min. "
    "Ne le communiquez à personne."
)


@dataclass(frozen=True)
class _Delivery:
    """Une tentative de livraison sur un canal Termii."""

    label: str  # "sms" ou "whatsapp" (journaux)
    channel: str  # valeur du champ `channel` de Termii
    sender: str
    text: str


def mask_phone(phone: str) -> str:
    """`+221771234567` -> `+221*******67` : assez pour diagnostiquer, sans
    exposer le numéro dans les journaux."""
    if len(phone) <= 6:
        return "*" * len(phone)
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


class TermiiSmsProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        api_key = settings.termii_api_key
        sender = settings.termii_sender_id
        base_url = settings.termii_base_url
        # Défense en profondeur : déjà exigés au démarrage (Settings.validate_termii).
        if not (api_key and sender and base_url):
            raise ValueError("Termii incomplet : voir TERMII_API_KEY, _SENDER_ID, _BASE_URL.")
        self._settings = settings
        self._api_key = api_key
        self._sender = sender
        self._base_url = base_url
        # Point d'injection des tests (faux serveur Termii, aucun réseau).
        self._transport = transport

    def _deliveries(self, code: str) -> list[_Delivery]:
        """Canaux à essayer, dans l'ordre fixé par OTP_CHANNEL."""
        settings = self._settings
        minutes = max(1, math.ceil(settings.otp_ttl_seconds / 60))
        sms = _Delivery(
            label="sms",
            channel=settings.otp_sms_channel,
            sender=self._sender,
            text=_SMS_TEMPLATE.format(code=code, minutes=minutes),
        )
        whatsapp_otp = settings.termii_whatsapp_channel == "whatsapp_otp"
        whatsapp = _Delivery(
            label="whatsapp",
            channel=settings.termii_whatsapp_channel,
            sender=settings.termii_whatsapp_sender or self._sender,
            # Canal de code WhatsApp : Termii n'accepte QUE les chiffres du code.
            text=code if whatsapp_otp else sms.text,
        )
        if settings.otp_channel == "whatsapp":
            return [whatsapp]
        if settings.otp_channel == "whatsapp_then_sms":
            return [whatsapp, sms]
        return [sms]

    async def send_otp(self, phone: str, code: str) -> None:
        deliveries = self._deliveries(code)
        masked = mask_phone(phone)
        try:
            async with (
                asyncio.timeout(self._settings.termii_total_timeout_seconds),
                httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._settings.termii_timeout_seconds,
                    transport=self._transport,
                ) as client,
            ):
                for delivery in deliveries:
                    if await self._deliver(client, delivery, phone, masked):
                        return
        except TimeoutError:
            logger.error(
                "Termii : budget total de %.1f s dépassé pour %s.",
                self._settings.termii_total_timeout_seconds,
                masked,
            )
        raise OtpEnvoiIndisponibleError()

    async def _deliver(
        self, client: httpx.AsyncClient, delivery: _Delivery, phone: str, masked: str
    ) -> bool:
        """Vrai si Termii confirme l'envoi sur ce canal."""
        payload = {
            "api_key": self._api_key,
            # Format international SANS « + » (exigence Termii).
            "to": phone.removeprefix("+"),
            "from": delivery.sender,
            "sms": delivery.text,
            "type": TERMII_MESSAGE_TYPE,
            "channel": delivery.channel,
        }
        attempts = self._settings.termii_max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = await client.post(TERMII_SEND_PATH, json=payload)
            except httpx.TransportError as exc:  # réseau, délai d'un appel
                logger.warning(
                    "Termii : %s vers %s, essai %d/%d : %s.",
                    delivery.label,
                    masked,
                    attempt,
                    attempts,
                    type(exc).__name__,
                )
            else:
                if response.is_success and _confirmed(response):
                    logger.info("Termii : code envoyé par %s à %s.", delivery.label, masked)
                    return True
                transient = response.status_code in _TRANSIENT_STATUSES
                logger.warning(
                    "Termii : %s vers %s refusé, essai %d/%d : HTTP %d (%s).",
                    delivery.label,
                    masked,
                    attempt,
                    attempts,
                    response.status_code,
                    "transitoire" if transient else "définitif",
                )
                if not transient:
                    return False  # erreur de requête : la répéter ne servirait à rien
            if attempt < attempts:
                await asyncio.sleep(_RETRY_PAUSE_SECONDS)
        return False


def _confirmed(response: httpx.Response) -> bool:
    """Succès documenté par Termii : `"code": "ok"` dans le corps JSON."""
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("code") == "ok"
