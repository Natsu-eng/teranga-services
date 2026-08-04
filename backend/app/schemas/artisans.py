"""Schémas Pydantic des artisans (BUILD_PLAN.md §3.2, §6 Lot 9).

Aucun champ de contact (`phone`/`email`) ni coordonnées brutes -- seule la
distance calculée (mètres, entier) est exposée quand `near` est fourni.
`service_area` (polygone) n'est jamais sérialisé brut non plus, seulement un
booléen dérivé -- même principe de protection que pour `base_location`
(BUILD_PLAN.md §2.2, anti-désintermédiation et vie privée géographique).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ArtisanVerifiedStatus,
    SubscriptionTier,
    VerificationDocType,
    VerificationStatus,
)
from app.schemas.requests import LocationIn
from app.schemas.trades import TradeOut


class ArtisanProfileUpdateIn(BaseModel):
    """`PATCH /artisans/me` (BUILD_PLAN.md §3.2, onboarding artisan).

    Tous les champs sont optionnels : seuls ceux réellement fournis dans le
    JSON sont appliqués (`model_dump(exclude_unset=True)` côté service), ce
    qui permet à un même endpoint de servir aussi bien le toggle historique
    (`{is_available}` seul, Lot 12c) que l'édition complète de l'onboarding.
    Ne porte jamais `verified_status` (toujours dérivé, jamais saisi) ni le
    rôle -- aucun des deux n'apparaît dans ce schéma."""

    is_available: bool | None = None
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    base_location: LocationIn | None = None
    avatar_url: str | None = Field(default=None, max_length=2000)


class ArtisanTradeCreateIn(BaseModel):
    trade_code: str
    hourly_rate_fcfa: int = Field(ge=0)
    service_radius_m: int = Field(gt=0, le=200_000)
    # Zone d'intervention précise, optionnelle -- polygone fermé (premier et
    # dernier point identiques), au moins 4 points (3 sommets + fermeture).
    # Si absente, la zone d'intervention retombe sur `service_radius_m`
    # autour de `base_location` (même règle que la recherche, BUILD_PLAN.md
    # §5.1).
    service_area: list[LocationIn] | None = Field(default=None, min_length=4)


class VerificationDocumentOut(BaseModel):
    """Métadonnées d'un document de vérification -- jamais son contenu
    binaire (BUILD_PLAN.md, onboarding artisan : `GET /artisans/me/documents`
    ne renvoie jamais le fichier lui-même, voir
    `GET /artisans/me/documents/{id}/content` pour ça)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_type: VerificationDocType
    status: VerificationStatus
    note: str | None
    created_at: datetime
    reviewed_at: datetime | None


class MyVerificationOut(BaseModel):
    verified_status: ArtisanVerifiedStatus
    documents: list[VerificationDocumentOut]


class ArtisanTradeOut(BaseModel):
    id: uuid.UUID
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
    # float, pas Decimal : Pydantic sérialise Decimal en chaîne JSON ("5.00"),
    # peu pratique côté frontend pour une note -- converti explicitement en
    # float à l'assemblage (app.services.artisans), jamais stocké ainsi
    # (la colonne DB reste Numeric(3,2), cf. app.models.artisan).
    rating_avg: float | None
    review_count: int
    distance_m: int | None
    trades: list[ArtisanTradeOut]


class ArtisanDetailOut(ArtisanListItemOut):
    cover_url: str | None
    created_at: datetime


class ArtisanStatsPublicOut(BaseModel):
    """Indicateurs de réputation, accessibles sans authentification."""

    rating_avg: float | None
    review_count: int
    interventions_count: int
    # Toujours `null` dans ce lot : aucun signal de réactivité artisan
    # (ex. `responded_at`) n'existe encore dans le modèle -- calcul réel
    # reporté à un lot qui ajoute ce tracking (BUILD_PLAN.md §6, Lot 9).
    response_rate: float | None


class ArtisanStatsPrivateOut(ArtisanStatsPublicOut):
    """Ajoute les statistiques financières -- artisan propriétaire ou admin
    uniquement (BUILD_PLAN.md §5, §6 Lot 9)."""

    revenue_fcfa: int
