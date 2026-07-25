"""Schémas Pydantic du devis (BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b).

Le devis est un objet autonome lié à l'intervention -- jamais un message de
chat (décision actée, BUILD_PLAN.md §6 Lot 12b) : la messagerie (lot
ultérieur) le référencera sans le contenir.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QuoteStatus


class QuoteCreateIn(BaseModel):
    labor_fcfa: int = Field(ge=0)
    materials_fcfa: int = Field(ge=0)


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    labor_fcfa: int
    materials_fcfa: int
    total_fcfa: int
    status: QuoteStatus
    created_at: datetime
