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

from app.models.enums import ArtisanVerifiedStatus, VerificationDocType, VerificationStatus
from app.schemas.artisans import ArtisanTradeOut, VerificationDocumentOut


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
