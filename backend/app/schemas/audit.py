"""Schémas du journal d'audit (lecture seule, admin)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AuditAction, AuditTargetType


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    # NULL : action hors application (script CLI de bootstrap).
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: AuditAction
    target_type: AuditTargetType
    target_id: uuid.UUID | None
    details: dict[str, Any]
