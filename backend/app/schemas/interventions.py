"""Schémas Pydantic de `/api/v1/interventions` (BUILD_PLAN.md §3.2, §6 Lot 12).

`commission_rate_bps` est exposé (transparence du taux figé) mais jamais
`commission_rate_id` -- l'identifiant est un détail d'implémentation, la
valeur en points de base est l'information utile au client et à l'artisan.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    EngagementBlocker,
    InterventionCancellationKind,
    InterventionStatus,
    Role,
)
from app.schemas.payments import DisputeOut, PaymentSummaryOut
from app.schemas.quotes import QuoteOut
from app.schemas.requests import ServiceRequestOut
from app.schemas.reviews import ReviewOut


class InterventionCreateIn(BaseModel):
    service_request_id: uuid.UUID
    artisan_id: uuid.UUID


class EngagementCheckOut(BaseModel):
    """Un artisan peut-il recevoir cette demande / ce lieu ? Même règle que
    `POST /interventions` (lecture seule) : le front marque AVANT l'envoi au
    lieu de découvrir un refus après coup."""

    eligible: bool
    # Premier obstacle rencontré, dans l'ordre de la règle ; `None` si éligible.
    reason: EngagementBlocker | None


class RequestEligibilityOut(EngagementCheckOut):
    request_id: uuid.UUID


class InterventionDeclineIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class CancellationOut(BaseModel):
    """Comment une intervention `annulee` a été close (BUILD_PLAN.md §3.5)."""

    kind: InterventionCancellationKind
    by: Role
    reason: str | None
    at: datetime


class InterventionOut(BaseModel):
    id: uuid.UUID
    service_request: ServiceRequestOut
    client_id: uuid.UUID
    artisan_id: uuid.UUID
    status: InterventionStatus
    commission_rate_bps: int
    agreed_amount_fcfa: int | None
    scheduled_at: datetime | None
    completed_at: datetime | None
    # Clôture d'une intervention `annulee` : refus, annulation ou arbitrage,
    # par qui et pourquoi (remplace l'ancien `decline_reason`).
    cancellation: CancellationOut | None = None
    quote: QuoteOut | None
    review: ReviewOut | None
    # Fil de discussion client ↔ artisan rattaché à cette intervention
    # (messagerie). Nul seulement si l'intervention n'a pas de fil, ce que la
    # migration c0a26cec109e a rattrapé pour les interventions existantes.
    conversation_id: uuid.UUID | None = None
    # Où en est l'argent (BUILD_PLAN.md §3.5) : total, commission au taux
    # figé, net de l'artisan, statut du paiement et du versement. `None`
    # tant qu'aucun devis n'est accepté. Visible des deux parties seulement
    # (et de l'admin), comme toute l'intervention.
    payment: PaymentSummaryOut | None = None
    dispute: DisputeOut | None = None
    created_at: datetime
