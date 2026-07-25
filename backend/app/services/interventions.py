"""Logique métier de `intervention` (BUILD_PLAN.md §2.2, §3.2, §6, §7 Lot 12).

Le cœur de l'entonnoir : la mise en relation entre un client et un artisan.
Fige le taux de commission en vigueur à l'instant de la création (résolu via
`app.services.commission`) -- ce taux ne bouge plus jamais pour cette
intervention, même si `commission_rate` change ensuite.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import ArtisanVerifiedStatus, Role, ServiceRequestStatus
from app.models.intervention import Intervention
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import interventions as interventions_repository
from app.repositories import requests as requests_repository
from app.repositories.requests import location_to_lat_lng
from app.schemas.interventions import InterventionCreateIn, InterventionOut
from app.schemas.pagination import Page
from app.services import commission as commission_service
from app.services import requests as requests_service
from app.services.artisans import PageHorsBornesError, get_artisan_or_404
from app.services.verification import compute_verified_status


class DemandeAutruiInterditeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_AUTRUI_INTERDITE",
            message="Cette demande n'appartient pas au client courant.",
            status_code=403,
        )


class DemandeNonOuverteError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_NON_OUVERTE",
            message="Cette demande n'est plus ouverte à une mise en relation.",
            status_code=409,
        )


class ArtisanNonVerifieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_NON_VERIFIE",
            message="Cet artisan n'est pas encore vérifié.",
            status_code=422,
        )


class ArtisanMetierNonExerceError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_METIER_NON_EXERCE",
            message="Cet artisan n'exerce pas le métier demandé.",
            status_code=422,
        )


class ArtisanHorsZoneError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_HORS_ZONE",
            message="Cet artisan ne couvre pas géographiquement cette demande.",
            status_code=422,
        )


class InterventionIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_NOT_FOUND", message="Intervention introuvable.", status_code=404
        )


class InterventionAccesInterditError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette intervention.",
            status_code=403,
        )


def _to_out(intervention: Intervention) -> InterventionOut:
    return InterventionOut(
        id=intervention.id,
        service_request=requests_service.to_service_request_out(intervention.service_request),
        client_id=intervention.client_id,
        artisan_id=intervention.artisan_id,
        status=intervention.status,
        commission_rate_bps=intervention.commission_rate.rate_bps,
        agreed_amount_fcfa=intervention.agreed_amount_fcfa,
        scheduled_at=intervention.scheduled_at,
        completed_at=intervention.completed_at,
        created_at=intervention.created_at,
    )


async def create_intervention(
    session: AsyncSession, *, client: User, payload: InterventionCreateIn, settings: Settings
) -> InterventionOut:
    """Crée la mise en relation (BUILD_PLAN.md §6 Lot 12). Ordre des règles :

    1. La demande existe, appartient au client courant, et est `ouverte`.
    2. L'artisan existe (compte actif, non supprimé).
    3. L'artisan est vérifié (`verified_status == VERIFIED`).
    4. L'artisan exerce le métier de la demande.
    5. La zone d'intervention de l'artisan (pour ce métier) couvre la
       position de la demande.
    6. Le taux de commission en vigueur pour ce métier est résolu et figé.

    La demande passe à `en_relation` -- elle ne peut plus recevoir d'autre
    intervention tant que celle-ci n'est pas close.
    """
    request = await requests_service.get_request_or_404(session, payload.service_request_id)
    if request.client_id != client.id:
        raise DemandeAutruiInterditeError()
    if request.status is not ServiceRequestStatus.OUVERTE:
        raise DemandeNonOuverteError()

    artisan = await get_artisan_or_404(session, payload.artisan_id)
    verified_status = compute_verified_status(
        artisan.verifications, settings.verification_required_doc_types
    )
    if verified_status is not ArtisanVerifiedStatus.VERIFIED:
        raise ArtisanNonVerifieError()

    exercises_trade = await artisans_repository.artisan_exercises_trade(
        session, artisan_id=artisan.id, trade_id=request.trade_id
    )
    if not exercises_trade:
        raise ArtisanMetierNonExerceError()

    lat, lng = location_to_lat_lng(request)
    reachable = await artisans_repository.is_artisan_reachable_for_trade(
        session, artisan_id=artisan.id, trade_id=request.trade_id, lat=lat, lng=lng
    )
    if not reachable:
        raise ArtisanHorsZoneError()

    rate = await commission_service.resolve_effective_commission_rate(
        session, trade_id=request.trade_id
    )

    intervention = await interventions_repository.create_intervention(
        session,
        service_request=request,
        client_id=client.id,
        artisan=artisan,
        commission_rate=rate,
    )
    await requests_repository.set_status(session, request, ServiceRequestStatus.EN_RELATION)

    return _to_out(intervention)


async def get_intervention_or_404(
    session: AsyncSession, intervention_id: uuid.UUID
) -> Intervention:
    intervention = await interventions_repository.get_by_id(session, intervention_id)
    if intervention is None:
        raise InterventionIntrouvableError()
    return intervention


async def get_intervention_for_user(
    session: AsyncSession, *, intervention_id: uuid.UUID, user: User
) -> InterventionOut:
    intervention = await get_intervention_or_404(session, intervention_id)
    if intervention.client_id == user.id or intervention.artisan.user_id == user.id:
        return _to_out(intervention)
    raise InterventionAccesInterditError()


async def list_my_interventions(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[InterventionOut]:
    """S'adapte au rôle de l'utilisateur courant (BUILD_PLAN.md §6 Lot 12) :
    un client voit ses interventions comme client, un artisan les siennes
    comme artisan -- jamais les deux à la fois, jamais celles d'autrui."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    if user.role is Role.ARTISAN:
        artisan_profile_id = await artisans_repository.get_artisan_profile_id_by_user_id(
            session, user.id
        )
        if artisan_profile_id is None:
            return Page.of([], page=page, page_size=resolved_page_size, total=0)
        interventions = await interventions_repository.list_for_artisan(
            session, artisan_profile_id, limit=resolved_page_size, offset=offset
        )
        total = await interventions_repository.count_for_artisan(session, artisan_profile_id)
    else:
        interventions = await interventions_repository.list_for_client(
            session, user.id, limit=resolved_page_size, offset=offset
        )
        total = await interventions_repository.count_for_client(session, user.id)

    items = [_to_out(intervention) for intervention in interventions]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)
