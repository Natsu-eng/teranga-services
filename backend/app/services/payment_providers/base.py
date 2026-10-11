"""Contrat d'un fournisseur de paiement (BUILD_PLAN.md §3.5).

Le code métier (`app.services.payments`) ne connaît QUE ce contrat : jamais
le nom, le format de webhook ni l'API d'un agrégateur précis. Un adaptateur
traduit son fournisseur vers ces types neutres -- c'est tout ce qu'il faut
écrire pour brancher Wave, PayDunya, CinetPay ou un autre.

Opérations sortantes (checkout, remboursement, versement) : toutes portent
une **clé d'idempotence** stable dérivée de nos identifiants. Rejouer un
appel (après un timeout, ou une transaction qui n'a pas pu être validée
chez nous) ne doit jamais créer un second remboursement ou un second
versement chez le fournisseur.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.models.enums import PaymentChannel, PayoutChannel

# Types d'événements normalisés. Tout autre type reçu d'un fournisseur est
# rapporté en "autre" et journalisé sans effet.
EventKind = Literal["checkout_reussi", "checkout_echoue", "autre"]


class PaymentProviderError(Exception):
    """Le fournisseur est injoignable ou a refusé l'opération."""


class InvalidWebhookSignatureError(Exception):
    """Signature absente, invalide ou trop ancienne : la notification ne
    vient pas (ou plus) du fournisseur."""


class MalformedWebhookError(Exception):
    """Notification correctement signée mais illisible."""


@dataclass(frozen=True)
class CheckoutRequest:
    # Notre identifiant de paiement : référence côté fournisseur ET clé
    # d'idempotence (un même paiement n'ouvre jamais deux checkouts).
    payment_id: str
    amount_fcfa: int
    currency: str
    channel: PaymentChannel
    description: str
    success_url: str
    error_url: str
    expires_at: datetime


@dataclass(frozen=True)
class CheckoutSession:
    provider_ref: str
    checkout_url: str
    expires_at: datetime


@dataclass(frozen=True)
class ProviderEvent:
    event_id: str
    kind: EventKind
    # Type brut du fournisseur, conservé pour l'audit.
    raw_type: str
    checkout_ref: str | None
    amount_fcfa: int | None
    currency: str | None


@dataclass(frozen=True)
class RefundRequest:
    provider_ref: str
    amount_fcfa: int
    currency: str
    idempotency_key: str


@dataclass(frozen=True)
class PayoutRequest:
    amount_fcfa: int
    currency: str
    channel: PayoutChannel
    # Numéro E.164 vérifié (OTP) du compte artisan -- jamais saisi à la volée.
    destination_phone: str
    idempotency_key: str
    description: str


@dataclass(frozen=True)
class ProviderOperation:
    """Accusé d'une opération acceptée par le fournisseur."""

    reference: str


class PaymentProvider(Protocol):
    """Ce qu'un adaptateur de fournisseur doit savoir faire."""

    @property
    def name(self) -> str:
        """Identifiant court et stable, stocké sur chaque paiement (ex. "sandbox")."""
        ...

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        """Ouvre une page de paiement hébergée par le fournisseur."""
        ...

    def verify_webhook_signature(self, payload: bytes, headers: Mapping[str, str]) -> None:
        """Lève `InvalidWebhookSignatureError` si la notification n'est pas
        authentique ou trop ancienne. Ne lit jamais le corps avant."""
        ...

    def parse_event(self, payload: bytes) -> ProviderEvent:
        """Traduit une notification authentifiée en événement normalisé ;
        lève `MalformedWebhookError` si elle est illisible."""
        ...

    async def refund(self, request: RefundRequest) -> ProviderOperation:
        """Rend au client les fonds d'un paiement retenu."""
        ...

    async def send_payout(self, request: PayoutRequest) -> ProviderOperation:
        """Verse un montant à l'artisan."""
        ...
