"""Schémas Pydantic de l'espace admin (BUILD_PLAN.md, revue des artisans).

Réservés aux routes `/api/v1/admin/*` -- jamais exposés ailleurs. Aucun
schéma d'entrée ne porte `role`/`verified_status` en écriture libre : le
premier n'est modifiable par aucun endpoint (voir `scripts/create_admin.py`,
seul chemin), le second reste toujours dérivé
(`app.services.verification.compute_verified_status`), jamais assigné
directement même par un admin -- seule l'approbation/le rejet d'un document
individuel peut le faire bouger, via le recalcul automatique.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ArtisanLocationSource,
    ArtisanVerifiedStatus,
    ReviewStatus,
    Role,
    VerificationDocType,
    VerificationStatus,
)
from app.schemas.artisans import ArtisanTradeOut, VerificationDocumentOut
from app.schemas.audit import AuditEntryOut


class AdminVerificationListItemOut(BaseModel):
    """Une ligne de la file d'attente de revue (`GET /admin/verifications`)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artisan_id: uuid.UUID
    artisan_full_name: str
    doc_type: VerificationDocType
    status: VerificationStatus
    note: str | None
    created_at: datetime
    reviewed_at: datetime | None


class VerificationRejectIn(BaseModel):
    # Motif obligatoire (BUILD_PLAN.md) : jamais de rejet muet -- l'artisan
    # doit savoir quoi corriger avant de renvoyer un document (Lot B,
    # `GET /artisans/me/documents` affiche déjà `note`).
    note: str = Field(min_length=3, max_length=1000)


class VerificationReviewOut(BaseModel):
    """Résultat d'une décision admin (`approve`/`reject`) -- porte à la fois
    l'état du document tranché et le `verified_status` résultant de
    l'artisan (recalculé, jamais assigné directement)."""

    id: uuid.UUID
    doc_type: VerificationDocType
    status: VerificationStatus
    note: str | None
    reviewed_by: uuid.UUID
    reviewed_at: datetime
    artisan_id: uuid.UUID
    artisan_verified_status: ArtisanVerifiedStatus


class AdminArtisanZoneOut(BaseModel):
    """Zone d'intervention vue par l'admin : d'où vient la position, sans
    la position elle-même (inutile pour décider, et jamais exposée)."""

    placed: bool
    source: ArtisanLocationSource | None
    neighborhood_id: str | None
    neighborhood_label: str | None


class AdminArtisanDetailOut(BaseModel):
    """Vue admin d'un artisan : profil + historique complet de ses documents
    (contrairement à `ArtisanDetailOut`, public, qui n'expose aucun
    document) -- pour décider en contexte (BUILD_PLAN.md)."""

    id: uuid.UUID
    full_name: str
    bio: str | None
    years_experience: int | None
    avatar_url: str | None
    is_available: bool
    verified_status: ArtisanVerifiedStatus
    trades: list[ArtisanTradeOut]
    documents: list[VerificationDocumentOut]
    # Back-office (BUILD_PLAN.md §3.6).
    phone: str
    created_at: datetime
    rating_avg: float | None
    review_count: int
    is_suspended: bool
    suspended_at: datetime | None
    suspension_reason: str | None
    # Zone d'intervention (rayons : dans `trades`).
    zone: AdminArtisanZoneOut
    # Interventions de l'artisan, par statut.
    interventions: dict[str, int]
    # Journal le concernant (décisions admin, changements de zone), plus
    # récents d'abord.
    history: list[AuditEntryOut]


class AdminArtisanListItemOut(BaseModel):
    """Une ligne de `GET /admin/artisans`."""

    id: uuid.UUID
    full_name: str
    phone: str
    verified_status: ArtisanVerifiedStatus
    is_suspended: bool
    trade_labels: list[str]
    rating_avg: float | None
    review_count: int
    pending_documents: int
    created_at: datetime


class ArtisanSuspendIn(BaseModel):
    # Motif obligatoire : jamais de sanction muette (journalisé, montré à l'artisan).
    reason: str = Field(min_length=10, max_length=1000)


class ArtisanReactivateIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AdminUserOut(BaseModel):
    """Un compte dans `GET /admin/users`, avec ce que l'admin peut en faire
    — et pourquoi pas (`guard`) : les garde-fous sont visibles avant l'action."""

    id: uuid.UUID
    full_name: str
    phone: str
    role: Role
    created_at: datetime
    has_artisan_profile: bool
    is_self: bool
    can_grant_admin: bool
    can_revoke_admin: bool
    guard: str | None


class AdminRoleChangeIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AdminReviewOut(BaseModel):
    """Un avis vu par la modération : auteur RÉEL (l'admin en a besoin pour
    juger), artisan concerné, signalement éventuel."""

    id: uuid.UUID
    rating: int
    comment: str
    status: ReviewStatus
    contact_verified: bool
    created_at: datetime
    intervention_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    artisan_id: uuid.UUID
    artisan_name: str
    report_reason: str | None
    reported_at: datetime | None


class ReviewHideIn(BaseModel):
    # Motif obligatoire : masquer une critique se justifie (journalisé).
    reason: str = Field(min_length=10, max_length=1000)


class ReviewRestoreIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
