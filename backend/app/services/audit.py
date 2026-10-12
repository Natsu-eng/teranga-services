"""Journal d'audit des actions admin sensibles (BUILD_PLAN.md §3.6).

`record` est appelé par CHAQUE service qui modifie l'état sur décision d'un
admin (document, litige, suspension, rôle, avis, taux de commission), dans
la même transaction que l'action : une action validée est toujours
journalisée, une action annulée ne l'est jamais. Le journal est en ajout
seul, garanti par la base (déclencheur `audit_log_append_only`).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditTargetType
from app.models.user import User
from app.repositories import audit as audit_repository
from app.repositories.audit import AuditFilters
from app.schemas.audit import AuditEntryOut
from app.schemas.pagination import Page
from app.services.artisans import PageHorsBornesError


def _jsonable(value: Any) -> Any:
    """Détails sérialisables en JSON, sans perte de sens (UUID, dates,
    énumérations, décimaux convertis en chaînes lisibles)."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


async def record(
    session: AsyncSession,
    *,
    actor: User | None,
    action: AuditAction,
    target_type: AuditTargetType,
    target_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Inscrit une action au journal. `actor=None` : script CLI (bootstrap)."""
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_name=actor.full_name if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=_jsonable(details or {}),
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_entries(
    session: AsyncSession,
    *,
    action: AuditAction | None,
    target_type: AuditTargetType | None,
    target_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AuditEntryOut]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)
    filters = AuditFilters(
        action=action, target_type=target_type, target_id=target_id, actor_id=actor_id
    )
    entries = await audit_repository.list_entries(
        session, filters, limit=resolved, offset=(page - 1) * resolved
    )
    total = await audit_repository.count_entries(session, filters)
    return Page.of(
        [AuditEntryOut.model_validate(entry) for entry in entries],
        page=page,
        page_size=resolved,
        total=total,
    )
