"""Accès données pour `service_request` (BUILD_PLAN.md §3.2, §6 Lot 12).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation) -- voir `app.services.requests` pour ça.
"""

import uuid

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
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
        urgency=urgency,
        ai_estimate_min_fcfa=ai_estimate_min_fcfa,
        ai_estimate_max_fcfa=ai_estimate_max_fcfa,
        status=ServiceRequestStatus.OUVERTE,
    )
    session.add(request)
    await session.flush()
    return request


async def get_by_id(session: AsyncSession, request_id: uuid.UUID) -> ServiceRequest | None:
    stmt = (
        select(ServiceRequest)
        .where(ServiceRequest.id == request_id)
        .options(joinedload(ServiceRequest.trade))
    )
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
