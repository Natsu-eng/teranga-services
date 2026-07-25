"""Schémas Pydantic de `/api/v1/interventions` (BUILD_PLAN.md §3.2, §6 Lot 12).

`commission_rate_bps` est exposé (transparence du taux figé) mais jamais
`commission_rate_id` -- l'identifiant est un détail d'implémentation, la
valeur en points de base est l'information utile au client et à l'artisan.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import InterventionStatus
from app.schemas.requests import ServiceRequestOut


class InterventionCreateIn(BaseModel):
    service_request_id: uuid.UUID
    artisan_id: uuid.UUID


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
    created_at: datetime
