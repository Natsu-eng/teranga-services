"""Schémas Pydantic des avis d'un artisan (BUILD_PLAN.md §3.2, §6 Lot 9, Lot 12b).

`author_name` seulement -- jamais l'id, le téléphone ou l'email de l'auteur.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    rating: int
    comment: str
    author_name: str
    created_at: datetime
