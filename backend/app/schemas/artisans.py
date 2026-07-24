"""Schémas Pydantic des artisans (BUILD_PLAN.md §3.2, §6 Lot 9).

Aucun champ de contact (`phone`/`email`) ni coordonnées brutes -- seule la
distance calculée (mètres, entier) est exposée quand `near` est fourni.
`service_area` (polygone) n'est jamais sérialisé brut non plus, seulement un
booléen dérivé -- même principe de protection que pour `base_location`
(BUILD_PLAN.md §2.2, anti-désintermédiation et vie privée géographique).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ArtisanVerifiedStatus, SubscriptionTier
from app.schemas.trades import TradeOut


class ArtisanTradeOut(BaseModel):
    trade: TradeOut
    hourly_rate_fcfa: int
    service_radius_m: int
    has_custom_service_area: bool


class ArtisanListItemOut(BaseModel):
    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    bio: str | None
    years_experience: int | None
    is_available: bool
    verified_status: ArtisanVerifiedStatus
    subscription_tier: SubscriptionTier
    rating_avg: Decimal | None
    review_count: int
    distance_m: int | None
    trades: list[ArtisanTradeOut]


class ArtisanDetailOut(ArtisanListItemOut):
    cover_url: str | None
    created_at: datetime
