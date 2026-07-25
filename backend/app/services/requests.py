"""Logique métier de `service_request` (BUILD_PLAN.md §3.2, §6 Lot 12).

Valide les entrées (métier actif, estimation IA re-vérifiée), assemble les
schémas de sortie depuis les entités ORM chargées par le repository -- jamais
l'inverse, le repository ne connaît pas Pydantic.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import Role
from app.models.request import ServiceRequest
from app.models.user import User
from app.repositories import interventions as interventions_repository
from app.repositories import requests as requests_repository
from app.repositories import trades as trades_repository
from app.repositories.requests import location_to_lat_lng
from app.schemas.pagination import Page
from app.schemas.requests import LocationOut, ServiceRequestCreateIn, ServiceRequestOut
from app.schemas.trades import TradeOut
from app.services.artisans import PageHorsBornesError


class MetierInconnuError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="METIER_INCONNU",
            message="Le métier demandé est introuvable ou inactif.",
            status_code=422,
        )


class EstimationIaInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ESTIMATION_IA_INVALIDE",
            message="L'estimation fournie est invalide.",
            status_code=422,
        )


class ServiceRequestIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SERVICE_REQUEST_NOT_FOUND", message="Demande introuvable.", status_code=404
        )


class ServiceRequestAccesInterditError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SERVICE_REQUEST_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette demande.",
            status_code=403,
        )


def _validate_ai_estimate(min_fcfa: int | None, max_fcfa: int | None) -> None:
    """Re-valide l'estimation IA optionnelle -- jamais fait confiance
    aveuglément à ce que le client transmet (BUILD_PLAN.md §6 Lot 12,
    AUDIT_PHASE2.md §6). Les deux bornes doivent être fournies ensemble
    (ou aucune), positives, et cohérentes (min <= max).
    """
    if min_fcfa is None and max_fcfa is None:
        return
    if min_fcfa is None or max_fcfa is None:
        raise EstimationIaInvalideError()
    if min_fcfa < 0 or max_fcfa < 0 or min_fcfa > max_fcfa:
        raise EstimationIaInvalideError()


def to_service_request_out(request: ServiceRequest) -> ServiceRequestOut:
    """Assemble `ServiceRequestOut` depuis une entité déjà chargée (avec
    `trade` eager-loadé) -- réutilisé par `app.services.interventions` pour
    nicher la demande dans `InterventionOut`."""
    lat, lng = location_to_lat_lng(request)
    return ServiceRequestOut(
        id=request.id,
        client_id=request.client_id,
        trade=TradeOut.model_validate(request.trade),
        description=request.description,
        photo_url=request.photo_url,
        location=LocationOut(lat=lat, lng=lng),
        urgency=request.urgency,
        ai_estimate_min_fcfa=request.ai_estimate_min_fcfa,
        ai_estimate_max_fcfa=request.ai_estimate_max_fcfa,
        status=request.status,
        created_at=request.created_at,
    )


async def create_request(
    session: AsyncSession, *, client: User, payload: ServiceRequestCreateIn
) -> ServiceRequestOut:
    trade = await trades_repository.get_active_trade_by_code(session, payload.trade_code)
    if trade is None:
        raise MetierInconnuError()

    _validate_ai_estimate(payload.ai_estimate_min_fcfa, payload.ai_estimate_max_fcfa)

    request = await requests_repository.create_service_request(
        session,
        client_id=client.id,
        trade=trade,
        description=payload.description,
        photo_url=payload.photo_url,
        lat=payload.location.lat,
        lng=payload.location.lng,
        urgency=payload.urgency,
        ai_estimate_min_fcfa=payload.ai_estimate_min_fcfa,
        ai_estimate_max_fcfa=payload.ai_estimate_max_fcfa,
    )
    return to_service_request_out(request)


async def get_request_or_404(session: AsyncSession, request_id: uuid.UUID) -> ServiceRequest:
    request = await requests_repository.get_by_id(session, request_id)
    if request is None:
        raise ServiceRequestIntrouvableError()
    return request


async def get_request_for_user(
    session: AsyncSession, *, request_id: uuid.UUID, user: User
) -> ServiceRequestOut:
    """Accessible au client propriétaire ou à l'artisan concerné (celui
    d'au moins une intervention liée à cette demande) -- personne d'autre,
    même authentifié (BUILD_PLAN.md §6 Lot 12)."""
    request = await get_request_or_404(session, request_id)

    if request.client_id == user.id:
        return to_service_request_out(request)
    if user.role is Role.ARTISAN:
        is_concerned = await interventions_repository.request_has_intervention_for_artisan_user(
            session, request_id=request_id, user_id=user.id
        )
        if is_concerned:
            return to_service_request_out(request)
    raise ServiceRequestAccesInterditError()


async def list_my_requests(
    session: AsyncSession, *, client: User, page: int, page_size: int, settings: Settings
) -> Page[ServiceRequestOut]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    requests = await requests_repository.list_by_client(
        session, client.id, limit=resolved_page_size, offset=offset
    )
    total = await requests_repository.count_by_client(session, client.id)

    items = [to_service_request_out(request) for request in requests]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)
