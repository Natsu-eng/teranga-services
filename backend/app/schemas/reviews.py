"""Schémas Pydantic des avis d'un artisan (BUILD_PLAN.md §3.2, §3.6, §6 Lot 9, Lot 12b).

`author_name` seulement -- jamais l'id, le téléphone ou l'email de l'auteur.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ReviewStatus


class ReviewCreateIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    rating: int
    comment: str
    author_name: str
    created_at: datetime
    # Statut de modération, dit tel quel (transparence) : `signale` = en
    # attente de décision, toujours visible et compté. La liste publique ne
    # sert jamais un avis `masque` ; seules les parties de l'intervention
    # (client auteur, artisan) le voient, avec ce statut.
    status: ReviewStatus


class ReviewReportIn(BaseModel):
    # Motif exigé : un signalement se justifie, il est lu par un admin.
    reason: str = Field(min_length=10, max_length=1000)


class ArtisanOwnReviewOut(BaseModel):
    """Un avis reçu, vu par l'artisan lui-même (`GET /artisans/me/reviews`),
    avec son statut de modération et la possibilité de le signaler."""

    id: uuid.UUID
    rating: int
    comment: str
    author_name: str
    created_at: datetime
    status: ReviewStatus
    report_reason: str | None
    reported_at: datetime | None
    can_report: bool
