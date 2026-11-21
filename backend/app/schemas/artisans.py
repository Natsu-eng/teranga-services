"""Schémas Pydantic des artisans (BUILD_PLAN.md §3.2, §6 Lot 9).

Aucun champ de contact (`phone`/`email`) ni coordonnées brutes -- seule la
distance, arrondie (PUBLIC_DISTANCE_ROUNDING_M), est exposée quand `near`
est fourni.
`service_area` (polygone) n'est jamais sérialisé brut non plus, seulement un
booléen dérivé -- même principe de protection que pour `base_location`
(BUILD_PLAN.md §2.2, anti-désintermédiation et vie privée géographique).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from app.models.enums import (
    ArtisanLocationSource,
    ArtisanVerifiedStatus,
    SubscriptionTier,
    VerificationDocType,
    VerificationStatus,
)
from app.schemas.requests import LocationIn
from app.schemas.trades import TradeOut


class NeighborhoodLocationIn(BaseModel):
    """Se placer au centre d'un quartier de la liste fermée : le serveur pose
    lui-même le centre officiel, aucune coordonnée n'est reçue."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["neighborhood"]
    neighborhood_id: str = Field(min_length=1, max_length=64)


class GpsLocationIn(BaseModel):
    """Se placer à sa position GPS : acceptée seulement dans la région
    desservie, puis arrondie sur la grille avant d'être enregistrée."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["gps"]
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


ArtisanLocationIn = Annotated[NeighborhoodLocationIn | GpsLocationIn, Field(discriminator="source")]


class ArtisanProfileUpdateIn(BaseModel):
    """`PATCH /artisans/me` (BUILD_PLAN.md §3.2, onboarding artisan).

    Tous les champs sont optionnels : seuls ceux réellement fournis dans le
    JSON sont appliqués (`model_dump(exclude_unset=True)` côté service), ce
    qui permet à un même endpoint de servir aussi bien le toggle historique
    (`{is_available}` seul, Lot 12c) que l'édition complète de l'onboarding.
    Ne porte jamais `verified_status` (toujours dérivé, jamais saisi) ni le
    rôle -- aucun des deux n'apparaît dans ce schéma."""

    is_available: bool | None = None
    # Vit sur `user.full_name`, pas sur `artisan_profile` -- appliqué à la
    # relation `profile.user` côté service (fix confidentialité du contact,
    # BUILD_PLAN.md). Bornes validées par `app.core.full_name.validate_full_name`,
    # pas ici : mêmes bornes que le signup, une seule source de vérité.
    full_name: str | None = None
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    # Zone d'intervention : un quartier ou une position GPS, rien d'autre.
    location: ArtisanLocationIn | None = None
    # Ancien format (coordonnées libres) : détecté pour être REFUSÉ avec un
    # message clair (FORMAT_POSITION_OBSOLETE), jamais appliqué ni ignoré en
    # silence. Hors du schéma OpenAPI.
    base_location: SkipJsonSchema[object | None] = Field(default=None, exclude=True)
    avatar_url: str | None = Field(default=None, max_length=2000)
    cover_url: str | None = Field(default=None, max_length=2000)

    @field_validator("avatar_url", "cover_url")
    @classmethod
    def _media_url_must_be_http(cls, value: str | None) -> str | None:
        # Ces deux URL sont rendues telles quelles dans un `<img src>` sur la
        # fiche PUBLIQUE : seul un schéma http(s) absolu est accepté, jamais
        # `javascript:`, `data:` ou un chemin relatif ambigu. Chaîne vide ou
        # blancs = « retirer la photo », ramené à `None` (même sens que
        # l'onboarding, qui envoie déjà `null` pour un champ vidé).
        if value is None:
            return None
        stripped = value.strip()
        if stripped == "":
            return None
        if not stripped.lower().startswith(("https://", "http://")):
            raise ValueError("L'URL de l'image doit commencer par https:// ou http://.")
        return stripped

    @field_validator("location", mode="before")
    @classmethod
    def _location_cannot_be_null(cls, value: object) -> object:
        # Un artisan ne se « déplace » pas vers nulle part : `location: null`
        # explicite est refusé (omettre le champ ne change rien).
        if value is None:
            raise ValueError("La zone d'intervention ne peut pas être vide.")
        return value


class MediaUploadLimitsOut(BaseModel):
    max_upload_bytes: int
    max_side_px: int


class ProfileMediaConstraintsOut(BaseModel):
    """`GET /artisans/me/media-constraints` : les contraintes d'envoi des
    photos de profil telles que le serveur les applique réellement -- seule
    source de vérité pour le pré-contrôle du front (jamais de plafond
    recopié en dur côté client)."""

    accepted_mime_types: list[str]
    max_pixels: int
    avatar: MediaUploadLimitsOut
    cover: MediaUploadLimitsOut


class ArtisanTradeCreateIn(BaseModel):
    trade_code: str
    hourly_rate_fcfa: int = Field(ge=0)
    # Plafond (ARTISAN_SERVICE_RADIUS_MAX_M) vérifié par le service.
    service_radius_m: int = Field(gt=0)
    # Zone d'intervention précise, optionnelle -- polygone fermé (premier et
    # dernier point identiques), au moins 4 points (3 sommets + fermeture).
    # Si absente, la zone d'intervention retombe sur `service_radius_m`
    # autour de `base_location` (même règle que la recherche, BUILD_PLAN.md
    # §5.1).
    service_area: list[LocationIn] | None = Field(default=None, min_length=4)


class ArtisanTradeRadiusUpdateIn(BaseModel):
    """`PATCH /artisans/me/trades/{id}` : nouveau rayon d'un métier, sans
    retirer le métier. Plafond vérifié par le service."""

    model_config = ConfigDict(extra="forbid")

    service_radius_m: int = Field(gt=0)


class ZoneNeighborhoodOut(BaseModel):
    id: str
    label: str
    department_label: str


class ZoneTradeOut(BaseModel):
    id: uuid.UUID
    trade: TradeOut
    service_radius_m: int
    has_custom_service_area: bool


class ArtisanZoneOut(BaseModel):
    """`GET /artisans/me/zone` : la zone d'intervention de l'artisan
    connecté, sans aucune coordonnée (il sait où il est ; ce qui compte est
    ce que le serveur a retenu et ce qu'il peut encore changer)."""

    placed: bool
    source: ArtisanLocationSource | None
    # Renseigné quand `source == "neighborhood"`.
    neighborhood: ZoneNeighborhoodOut | None
    trades: list[ZoneTradeOut]
    radius_max_m: int
    gps_grid_m: int
    # Changements encore possibles sur chaque fenêtre (le premier placement
    # ne compte pas).
    changes_remaining_short: int
    changes_remaining_long: int
    short_window_hours: int
    long_window_days: int
    # Quand un changement redevient possible, si aucun ne l'est (UTC).
    next_change_at: datetime | None


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
    # Lu seulement par l'artisan lui-même (et l'admin) : la fiche d'un
    # artisan suspendu n'est plus servie au public (404). Le motif lui est
    # donc montré sans jamais fuiter : jamais de sanction muette.
    is_suspended: bool = False
    suspension_reason: str | None = None


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
