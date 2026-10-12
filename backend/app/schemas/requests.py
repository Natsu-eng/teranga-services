"""Schémas Pydantic de `/api/v1/requests` (BUILD_PLAN.md §3.2, §6 Lot 12).

`ai_estimate_min_fcfa`/`ai_estimate_max_fcfa` sont acceptés en entrée (issus
du triage IA, `POST /ai/analyze`) mais jamais fait confiance aveuglément --
re-validés côté serveur par `app.services.requests` avant écriture.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ServiceRequestStatus, Urgency
from app.models.request import LOCATION_LABEL_MAX_LENGTH
from app.schemas.trades import TradeOut


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class LocationOut(BaseModel):
    lat: float
    lng: float


class ServiceRequestCreateIn(BaseModel):
    trade_code: str
    description: str = Field(min_length=1, max_length=2000)
    photo_url: str | None = None
    location: LocationIn
    # Lieu confirmé par le client (quartier choisi ou « Ma position
    # actuelle ») : ce qu'il a VU avant d'envoyer, jamais deviné ici.
    location_label: str | None = Field(default=None, max_length=LOCATION_LABEL_MAX_LENGTH)
    urgency: Urgency = Urgency.NORMAL
    # Issus du triage IA (POST /ai/analyze) -- optionnels, re-validés côté
    # serveur (app.services.requests), jamais persistés tels quels.
    ai_estimate_min_fcfa: int | None = None
    ai_estimate_max_fcfa: int | None = None

    @field_validator("location_label")
    @classmethod
    def _clean_location_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class ServiceRequestOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    trade: TradeOut
    description: str
    photo_url: str | None
    location: LocationOut
    location_label: str | None = None
    urgency: Urgency
    ai_estimate_min_fcfa: int | None
    ai_estimate_max_fcfa: int | None
    status: ServiceRequestStatus
    # Demande ouverte : date à laquelle elle expirera sans artisan (sinon null).
    expires_at: datetime | None = None
    created_at: datetime
