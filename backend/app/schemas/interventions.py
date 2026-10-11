"""Schémas Pydantic de `/api/v1/interventions` (BUILD_PLAN.md §3.2, §6 Lot 12).

`commission_rate_bps` est exposé (transparence du taux figé) mais jamais
`commission_rate_id` -- l'identifiant est un détail d'implémentation, la
valeur en points de base est l'information utile au client et à l'artisan.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import InterventionCancellationKind, InterventionStatus, Role
from app.schemas.quotes import QuoteOut
from app.schemas.requests import ServiceRequestOut
from app.schemas.reviews import ReviewOut


class InterventionCreateIn(BaseModel):
    service_request_id: uuid.UUID
    artisan_id: uuid.UUID


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
    cancellation: CancellationOut | None = None
    # Compatibilité : motif du refus par l'artisan (= `cancellation.reason`
    # quand `cancellation.kind == "refus"`), conservé tant que des clients
    # le lisent encore.
    decline_reason: str | None
    quote: QuoteOut | None
    review: ReviewOut | None
    # Fil de discussion client ↔ artisan rattaché à cette intervention
    # (messagerie). Nul seulement si l'intervention n'a pas de fil, ce que la
    # migration c0a26cec109e a rattrapé pour les interventions existantes.
    conversation_id: uuid.UUID | None = None
    created_at: datetime
