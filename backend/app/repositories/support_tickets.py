"""Accès aux demandes d'aide (`support_ticket`)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.enums import SupportTicketStatus
from app.models.intervention import Intervention
from app.models.request import ServiceRequest
from app.models.support import SupportTicket

# Auteur et métier de l'intervention liée, chargés d'avance (aucune requête
# paresseuse, impossible en asynchrone).
_DISPLAY_RELATIONS = (
    joinedload(SupportTicket.author),
    joinedload(SupportTicket.intervention)
    .joinedload(Intervention.service_request)
    .joinedload(ServiceRequest.trade),
)


async def list_for_author(
    session: AsyncSession, author_id: uuid.UUID, *, limit: int, offset: int
) -> list[SupportTicket]:
    """Demandes d'UN auteur seulement, plus récentes d'abord."""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.author_id == author_id)
        .options(*_DISPLAY_RELATIONS)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.unique().scalars())


async def count_for_author(session: AsyncSession, author_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.author_id == author_id)
        )
    ).scalar_one()


async def list_by_status(
    session: AsyncSession, status: SupportTicketStatus, *, limit: int, offset: int
) -> list[SupportTicket]:
    """File admin : demandes ouvertes, la plus ancienne d'abord (premier
    arrivé, premier servi) ; résolues, la plus récente d'abord."""
    order = (
        (SupportTicket.created_at.asc(), SupportTicket.id)
        if status is SupportTicketStatus.OUVERT
        else (SupportTicket.resolved_at.desc(), SupportTicket.id)
    )
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status == status)
        .options(*_DISPLAY_RELATIONS)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    )
    return list(result.unique().scalars())


async def count_by_status(session: AsyncSession, status: SupportTicketStatus) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == status)
        )
    ).scalar_one()


async def get_for_update(session: AsyncSession, ticket_id: uuid.UUID) -> SupportTicket | None:
    """Verrou de ligne : deux admins qui répondent en même temps sont
    sérialisés (le second voit l'état laissé par le premier)."""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(*_DISPLAY_RELATIONS)
        .with_for_update(of=SupportTicket)
        .execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()


async def get_with_relations(session: AsyncSession, ticket_id: uuid.UUID) -> SupportTicket | None:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(*_DISPLAY_RELATIONS)
        .execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()
