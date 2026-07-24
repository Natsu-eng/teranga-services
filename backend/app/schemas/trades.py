"""Schémas Pydantic du référentiel des métiers (`GET /api/v1/trades`)."""

import uuid

from pydantic import BaseModel, ConfigDict


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    label_fr: str
    label_wo: str | None
    icon: str | None
    sort_order: int
