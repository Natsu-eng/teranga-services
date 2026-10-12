"""Accès données pour `service_request` (BUILD_PLAN.md §3.2, §6 Lot 12).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation) -- voir `app.services.requests` pour ça.
"""

import uuid
from datetime import datetime

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.enums import ServiceRequestStatus, Urgency
from app.models.request import ServiceRequest
from app.models.trade import Trade


def to_point(*, lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def location_to_lat_lng(request: ServiceRequest) -> tuple[float, float]:
    """Reconvertit `location` (geography Point) en (lat, lng) pour la sortie API."""
    shape = to_shape(request.location)
    return shape.y, shape.x


async def create_service_request(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    trade: Trade,
    description: str,
    photo_url: str | None,
    lat: float,
    lng: float,
    location_label: str | None,
    urgency: Urgency,
    ai_estimate_min_fcfa: int | None,
    ai_estimate_max_fcfa: int | None,
) -> ServiceRequest:
    # `trade=trade` (pas `trade_id=trade.id`) : peuple la relation en mémoire
    # immédiatement, sans requête -- la sortie API peut lire `request.trade`
    # sans déclencher un lazy load hors contexte async (MissingGreenlet).
    request = ServiceRequest(
        client_id=client_id,
        trade=trade,
        description=description,
        photo_url=photo_url,
        location=to_point(lat=lat, lng=lng),
        location_label=location_label,
        urgency=urgency,
        ai_estimate_min_fcfa=ai_estimate_min_fcfa,
        ai_estimate_max_fcfa=ai_estimate_max_fcfa,
        status=ServiceRequestStatus.OUVERTE,
    )
    session.add(request)
    await session.flush()
    return request


async def get_by_id(
    session: AsyncSession, request_id: uuid.UUID, *, for_update: bool = False
) -> ServiceRequest | None:
    """`for_update` : verrouille la ligne jusqu'à la fin de la transaction --
    toute décision sur le STATUT d'une demande (annulation, mise en
    relation) passe par ce verrou, donc jamais deux décisions concurrentes."""
    stmt = (
        select(ServiceRequest)
        .where(ServiceRequest.id == request_id)
        .options(joinedload(ServiceRequest.trade))
    )
    if for_update:
        stmt = stmt.with_for_update(of=ServiceRequest).execution_options(populate_existing=True)
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def list_by_client(
    session: AsyncSession, client_id: uuid.UUID, *, limit: int, offset: int
) -> list[ServiceRequest]:
    stmt = (
        select(ServiceRequest)
        .where(ServiceRequest.client_id == client_id)
        .options(joinedload(ServiceRequest.trade))
        # Tie-breaker `id` : pagination déterministe entre deux pages même
        # pour deux demandes créées à la même seconde.
        .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def list_open_by_client(
    session: AsyncSession, client_id: uuid.UUID, *, created_after: datetime, limit: int
) -> list[ServiceRequest]:
    """Demandes encore ouvertes ET non expirées du client, les plus récentes
    d'abord."""
    stmt = (
        select(ServiceRequest)
        .where(
            ServiceRequest.client_id == client_id,
            ServiceRequest.status == ServiceRequestStatus.OUVERTE,
            ServiceRequest.created_at > created_after,
        )
        .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def expire_open_created_before(session: AsyncSession, cutoff: datetime) -> int:
    """Passe `expiree` toute demande encore OUVERTE créée avant `cutoff`.
    La condition est réévaluée par Postgres sur chaque ligne verrouillée :
    une demande mise en relation entre-temps n'est jamais expirée."""
    stmt = (
        update(ServiceRequest)
        .where(
            ServiceRequest.status == ServiceRequestStatus.OUVERTE,
            ServiceRequest.created_at <= cutoff,
        )
        .values(status=ServiceRequestStatus.EXPIREE)
        .returning(ServiceRequest.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.execute(stmt)).scalars().all())


async def count_by_client(session: AsyncSession, client_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(ServiceRequest)
        .where(ServiceRequest.client_id == client_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def set_status(
    session: AsyncSession, request: ServiceRequest, status: ServiceRequestStatus
) -> None:
    request.status = status
    await session.flush()
