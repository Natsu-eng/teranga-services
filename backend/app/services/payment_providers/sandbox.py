"""Fournisseur sandbox : reproduit le CONTRAT d'un agrégateur, sans argent réel.

Ce qu'il simule fidèlement (BUILD_PLAN.md §3.5) :

- **Checkout hébergé** : `create_checkout` renvoie l'URL d'une page de
  paiement servie hors du front (`/api/v1/sandbox/checkout/...`, comme la
  page d'un agrégateur). Son jeton est signé et expire : il ne peut pas
  être modifié (montant, retour) ni réutilisé indéfiniment.
- **Webhook signé** : la page « paie » ou « échoue » puis livre une
  notification JSON au backend, comme un fournisseur réel, avec l'en-tête
  `Teranga-Sandbox-Signature: t=<horodatage>,v1=<hmac>` --
  HMAC-SHA256(secret, "<t>.<corps>") ; plusieurs `v1` sont acceptés
  (rotation du secret). Horodatage trop ancien = refus (rejeu).
- **Event id** : chaque notification porte un identifiant unique (`EV_...`),
  rejoué tel quel lors d'une nouvelle tentative de livraison.
- **Montants en chaîne** (« "12000" »), comme Wave : jamais de float.
- **Remboursement / versement** : acceptés immédiatement, avec une
  référence DÉTERMINISTE dérivée de la clé d'idempotence -- rejouer la même
  opération rend la même référence, jamais une seconde opération.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

import jwt

from app.services.payment_providers.base import (
    CheckoutRequest,
    CheckoutSession,
    EventKind,
    InvalidWebhookSignatureError,
    MalformedWebhookError,
    PayoutRequest,
    ProviderEvent,
    ProviderOperation,
    RefundRequest,
)

PROVIDER_NAME = "sandbox"
SIGNATURE_HEADER = "Teranga-Sandbox-Signature"
CHECKOUT_PATH = "/api/v1/sandbox/checkout"
# Types bruts émis par le sandbox, calqués sur ceux de Wave.
EVENT_COMPLETED = "checkout.session.completed"
EVENT_FAILED = "checkout.session.payment_failed"
_EVENT_KINDS: dict[str, EventKind] = {
    EVENT_COMPLETED: "checkout_reussi",
    EVENT_FAILED: "checkout_echoue",
}
_TOKEN_AUDIENCE = "teranga-sandbox-checkout"
_AMOUNT_PATTERN = re.compile(r"^[0-9]{1,12}$")

SandboxOutcome = Literal["paye", "echoue"]


def _digest(prefix: str, key: str) -> str:
    return f"{prefix}{hashlib.sha256(key.encode()).hexdigest()[:24]}"


def sign_payload(secret: str, payload: bytes, *, timestamp: int | None = None) -> str:
    """Valeur de l'en-tête de signature pour `payload` (utilisé par la page
    sandbox pour livrer ses notifications, et par les tests)."""
    signed_at = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{signed_at}.".encode() + payload, hashlib.sha256)
    return f"t={signed_at},v1={mac.hexdigest()}"


class SandboxProvider:
    """Adaptateur sandbox du contrat `PaymentProvider`."""

    def __init__(
        self,
        *,
        webhook_secret: str,
        checkout_base_url: str,
        tolerance_seconds: int,
    ) -> None:
        self._webhook_secret = webhook_secret
        # Clé distincte pour les jetons de checkout : un jeton ne peut jamais
        # servir de signature de webhook, et inversement.
        self._token_key = hmac.new(
            webhook_secret.encode(), b"teranga-sandbox-checkout-token", hashlib.sha256
        ).hexdigest()
        self._checkout_base_url = checkout_base_url.rstrip("/")
        self._tolerance_seconds = tolerance_seconds

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    # ------------------------------------------------------------ checkout

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        provider_ref = _digest("sbx_cs_", request.payment_id)
        token = jwt.encode(
            {
                "aud": _TOKEN_AUDIENCE,
                "ref": provider_ref,
                "pid": request.payment_id,
                "amt": request.amount_fcfa,
                "cur": request.currency,
                "ch": request.channel.value,
                "desc": request.description,
                "ok": request.success_url,
                "ko": request.error_url,
                "exp": int(request.expires_at.timestamp()),
            },
            self._token_key,
            algorithm="HS256",
        )
        return CheckoutSession(
            provider_ref=provider_ref,
            checkout_url=f"{self._checkout_base_url}{CHECKOUT_PATH}/{token}",
            expires_at=request.expires_at,
        )

    def read_checkout_token(self, token: str) -> dict[str, Any]:
        """Décode le jeton d'une page de paiement ; lève
        `InvalidWebhookSignatureError` s'il est falsifié ou expiré."""
        try:
            claims: dict[str, Any] = jwt.decode(
                token, self._token_key, algorithms=["HS256"], audience=_TOKEN_AUDIENCE
            )
        except jwt.PyJWTError as exc:
            raise InvalidWebhookSignatureError("Page de paiement invalide ou expirée.") from exc
        return claims

    def build_event(self, claims: Mapping[str, Any], outcome: SandboxOutcome) -> bytes:
        """Notification JSON qu'enverrait l'agrégateur pour ce checkout."""
        event = {
            "id": f"EV_{uuid.uuid4().hex}",
            "type": EVENT_COMPLETED if outcome == "paye" else EVENT_FAILED,
            "data": {
                "id": claims["ref"],
                "amount": str(claims["amt"]),
                "currency": claims["cur"],
                "client_reference": claims["pid"],
                "checkout_status": "complete" if outcome == "paye" else "failed",
                "when_completed": datetime.now(UTC).isoformat(),
            },
        }
        return json.dumps(event, separators=(",", ":")).encode()

    def sign(self, payload: bytes) -> str:
        return sign_payload(self._webhook_secret, payload)

    # ------------------------------------------------------------ webhooks

    def verify_webhook_signature(self, payload: bytes, headers: Mapping[str, str]) -> None:
        header = next(
            (value for key, value in headers.items() if key.lower() == SIGNATURE_HEADER.lower()),
            None,
        )
        if not header:
            raise InvalidWebhookSignatureError("Signature absente.")

        timestamp: int | None = None
        signatures: list[str] = []
        for part in header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "t" and value.isdigit():
                timestamp = int(value)
            elif key == "v1" and value:
                signatures.append(value)
        if timestamp is None or not signatures:
            raise InvalidWebhookSignatureError("Signature mal formée.")
        if abs(time.time() - timestamp) > self._tolerance_seconds:
            raise InvalidWebhookSignatureError("Signature trop ancienne.")

        expected = hmac.new(
            self._webhook_secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
        ).hexdigest()
        # Comparaison à temps constant : ne révèle rien du secret.
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise InvalidWebhookSignatureError("Signature invalide.")

    def parse_event(self, payload: bytes) -> ProviderEvent:
        try:
            event = json.loads(payload)
            event_id = event["id"]
            raw_type = event["type"]
            data = event.get("data") or {}
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise MalformedWebhookError("Notification illisible.") from exc
        if not isinstance(event_id, str) or not event_id or not isinstance(raw_type, str):
            raise MalformedWebhookError("Identifiant ou type d'événement manquant.")
        if not isinstance(data, dict):
            raise MalformedWebhookError("Données d'événement illisibles.")

        amount = data.get("amount")
        if amount is not None and (
            not isinstance(amount, str) or not _AMOUNT_PATTERN.fullmatch(amount)
        ):
            # Jamais d'interprétation d'un montant douteux (décimales, signe).
            raise MalformedWebhookError("Montant illisible.")
        checkout_ref = data.get("id")
        currency = data.get("currency")
        return ProviderEvent(
            event_id=event_id,
            kind=_EVENT_KINDS.get(raw_type, "autre"),
            raw_type=raw_type,
            checkout_ref=checkout_ref if isinstance(checkout_ref, str) else None,
            amount_fcfa=int(amount) if amount is not None else None,
            currency=currency if isinstance(currency, str) else None,
        )

    # ------------------------------------------------------------ opérations

    async def refund(self, request: RefundRequest) -> ProviderOperation:
        return ProviderOperation(reference=_digest("sbx_rf_", request.idempotency_key))

    async def send_payout(self, request: PayoutRequest) -> ProviderOperation:
        return ProviderOperation(reference=_digest("sbx_po_", request.idempotency_key))
