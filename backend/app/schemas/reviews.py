"""Schémas Pydantic des avis publics d'un artisan (BUILD_PLAN.md §3.2, §6 Lot 9).

`author_name` seulement -- jamais l'id, le téléphone ou l'email de l'auteur.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReviewOut(BaseModel):
    id: uuid.UUID
    rating: int
    comment: str
    author_name: str
    created_at: datetime
