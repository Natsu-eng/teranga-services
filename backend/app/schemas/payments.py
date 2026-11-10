"""Schémas Pydantic des paiements (BUILD_PLAN.md §3.5).

Tous les montants sont des ENTIERS de FCFA, le taux en points de base. Le
résumé financier d'une intervention (`PaymentSummaryOut`) n'est servi
qu'à ses deux parties et à l'admin : il voyage dans `InterventionOut`, que
seules ces personnes peuvent lire.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    DisputeOutcome,
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PayoutChannel,
    PayoutStatus,
    PlatformFeeStatus,
    Role,
)
from app.schemas.pagination import PaginationMeta


class PaymentOptionsOut(BaseModel):
    """Moyens de paiement réellement disponibles (le front n'en affiche
    jamais d'autres)."""

    online_channels: list[PaymentChannel]
    # Moyens en ligne PRÉVUS mais pas encore actifs (PAYMENT_ONLINE_CHANNELS
    # avec PAYMENT_PROVIDER=disabled) : le front les montre « Bientôt »,
    # jamais comme utilisables. Vide dès que le paiement en ligne est actif.
    upcoming_channels: list[PaymentChannel]
    cash_enabled: bool
    currency: str


class PaymentInitIn(BaseModel):
    intervention_id: uuid.UUID
    channel: PaymentChannel
    # Aucun montant ici, volontairement : il vient TOUJOURS du devis accepté.


class CommissionOut(BaseModel):
    rate_bps: int
    amount_fcfa: int
    # `None` tant qu'aucune commission n'est enregistrée : le montant est
    # alors une estimation sur le devis accepté et le taux figé.
    status: PlatformFeeStatus | None


class PayoutOut(BaseModel):
    status: PayoutStatus
    amount_fcfa: int
    channel: PayoutChannel
    sent_at: datetime | None


class PaymentSummaryOut(BaseModel):
    """Où en est l'argent d'une intervention : total payé par le client,
    commission de Téranga, net de l'artisan, et chaque étape datée."""

    # Montant convenu (devis accepté) : ce que paie le client, sans frais ajoutés.
    amount_fcfa: int
    commission: CommissionOut
    # Ce que touche l'artisan : montant - commission (au franc près).
    net_fcfa: int
    # `None` : aucun paiement initié.
    status: PaymentStatus | None
    channel: PaymentChannel | None
    checkout_url: str | None
    checkout_expires_at: datetime | None
    paid_at: datetime | None
    released_at: datetime | None
    refunded_at: datetime | None
    payout: PayoutOut | None
    # Le paiement en ligne (séquestre) est-il proposé sur cette plateforme ?
    # Faux au lancement « espèces seulement » (PAYMENT_PROVIDER=disabled) :
    # l'interface ne promet alors ni séquestre ni « payer en ligne ».
    online_available: bool


class PayoutSettingsOut(BaseModel):
    """Où l'artisan reçoit ses versements. Le numéro n'est jamais saisi :
    c'est toujours celui de son compte, vérifié par OTP."""

    channel: PayoutChannel
    # Faux tant que l'artisan s'en remet au moyen par défaut.
    chosen: bool
    allowed_channels: list[PayoutChannel]
    destination_phone: str


class PayoutSettingsIn(BaseModel):
    channel: PayoutChannel


class DisputeOut(BaseModel):
    opened_by: Role
    reason: str
    opened_at: datetime
    outcome: DisputeOutcome | None
    resolved_at: datetime | None
    resolution_note: str | None


class InterventionCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class DisputeOpenIn(BaseModel):
    # Un litige gèle l'argent : il doit être expliqué.
    reason: str = Field(min_length=10, max_length=2000)


class DisputeResolveIn(BaseModel):
    outcome: DisputeOutcome
    note: str = Field(min_length=3, max_length=2000)


class ClientPaymentOut(BaseModel):
    """Un paiement dans l'historique du client."""

    id: uuid.UUID
    intervention_id: uuid.UUID
    trade_label: str
    artisan_name: str
    amount_fcfa: int
    channel: PaymentChannel
    status: PaymentStatus
    created_at: datetime
    paid_at: datetime | None
    released_at: datetime | None
    refunded_at: datetime | None


class EarningsTotalsOut(BaseModel):
    """Synthèse des gains d'un artisan, en FCFA."""

    # Net déjà versé sur son compte.
    paid_out_fcfa: int
    # Net libéré, versement en cours (ou à relancer).
    payout_pending_fcfa: int
    # Net encore en séquestre (travaux en cours, payés en ligne).
    in_escrow_fcfa: int
    # Commissions prélevées par Téranga sur les versements.
    commission_collected_fcfa: int
    # Espèces encaissées directement.
    cash_received_fcfa: int
    # Commissions dues par l'artisan sur des travaux réglés hors séquestre.
    commission_due_fcfa: int


class EarningItemOut(BaseModel):
    intervention_id: uuid.UUID
    trade_label: str
    client_name: str
    intervention_status: InterventionStatus
    payment: PaymentSummaryOut


class ArtisanEarningsOut(BaseModel):
    totals: EarningsTotalsOut
    # Même format de pagination que partout ailleurs dans l'API.
    items: list[EarningItemOut]
    pagination: PaginationMeta
