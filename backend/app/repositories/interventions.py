"""Accès données pour `intervention` (BUILD_PLAN.md §3.2, §6 Lot 12).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation) -- voir `app.services.interventions` pour ça.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.artisan import ArtisanProfile
from app.models.intervention import Intervention
from app.models.request import ServiceRequest


async def request_has_intervention_for_artisan_user(
    session: AsyncSession, *, request_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Vrai si `user_id` est l'artisan d'au moins une intervention liée à
    `request_id` -- l'artisan est alors "concerné" par cette demande
    (`GET /requests/{id}`, BUILD_PLAN.md §6 Lot 12)."""
    stmt = (
        select(Intervention.id)
        .join(ArtisanProfile, ArtisanProfile.id == Intervention.artisan_id)
        .where(Intervention.service_request_id == request_id, ArtisanProfile.user_id == user_id)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


def _eager_load(
    stmt: Select[tuple[Intervention]],
) -> Select[tuple[Intervention]]:
    return stmt.options(
        joinedload(Intervention.service_request).joinedload(ServiceRequest.trade),
        joinedload(Intervention.artisan).joinedload(ArtisanProfile.user),
    )


async def create_intervention(
    session: AsyncSession,
    *,
    service_request_id: uuid.UUID,
    client_id: uuid.UUID,
    artisan_id: uuid.UUID,
    commission_rate_id: uuid.UUID,
) -> Intervention:
    intervention = Intervention(
        service_request_id=service_request_id,
        client_id=client_id,
        artisan_id=artisan_id,
        commission_rate_id=commission_rate_id,
    )
    session.add(intervention)
    await session.flush()
    return intervention


async def get_by_id(session: AsyncSession, intervention_id: uuid.UUID) -> Intervention | None:
    stmt = _eager_load(select(Intervention).where(Intervention.id == intervention_id))
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def list_for_client(
    session: AsyncSession, client_id: uuid.UUID, *, limit: int, offset: int
) -> list[Intervention]:
    stmt = _eager_load(select(Intervention).where(Intervention.client_id == client_id))
    stmt = (
        stmt.order_by(Intervention.created_at.desc(), Intervention.id).limit(limit).offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_for_client(session: AsyncSession, client_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Intervention).where(Intervention.client_id == client_id)
    return (await session.execute(stmt)).scalar_one()


async def list_for_artisan(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int, offset: int
) -> list[Intervention]:
    stmt = _eager_load(select(Intervention).where(Intervention.artisan_id == artisan_id))
    stmt = (
        stmt.order_by(Intervention.created_at.desc(), Intervention.id).limit(limit).offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_for_artisan(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count()).select_from(Intervention).where(Intervention.artisan_id == artisan_id)
    )
    return (await session.execute(stmt)).scalar_one()
