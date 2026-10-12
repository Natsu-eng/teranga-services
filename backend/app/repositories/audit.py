"""Accès données du journal d'audit : insertion et lecture SEULEMENT.

Aucune fonction de mise à jour ni de suppression -- et la base les refuse de
toute façon (déclencheur `audit_log_append_only`).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditTargetType


@dataclass(frozen=True)
class AuditFilters:
    action: AuditAction | None = None
    target_type: AuditTargetType | None = None
    target_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None


def _conditions(filters: AuditFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.action is not None:
        conditions.append(AuditLog.action == filters.action)
    if filters.target_type is not None:
        conditions.append(AuditLog.target_type == filters.target_type)
    if filters.target_id is not None:
        conditions.append(AuditLog.target_id == filters.target_id)
    if filters.actor_id is not None:
        conditions.append(AuditLog.actor_id == filters.actor_id)
    return conditions


async def list_entries(
    session: AsyncSession, filters: AuditFilters, *, limit: int, offset: int
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(*_conditions(filters))
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_entries(session: AsyncSession, filters: AuditFilters) -> int:
    stmt = select(func.count()).select_from(AuditLog).where(*_conditions(filters))
    return (await session.execute(stmt)).scalar_one()


async def list_for_artisan(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int
) -> list[AuditLog]:
    """Décisions concernant un artisan : celles qui le ciblent (suspension,
    réactivation) et celles sur ses documents (détail `artisan_id`)."""
    stmt = (
        select(AuditLog)
        .where(
            or_(
                and_(
                    AuditLog.target_type == AuditTargetType.ARTISAN,
                    AuditLog.target_id == artisan_id,
                ),
                AuditLog.details["artisan_id"].astext == str(artisan_id),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
