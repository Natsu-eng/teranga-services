"""Règle d'engagement unique (BUILD_PLAN.md §3.2, lot `fix/localisation-demande`) :
un artisan peut-il recevoir une demande de ce métier, à ce lieu ?

Extraite de `app.services.interventions` sans changement de logique : la
même évaluation sert à la création d'une intervention, à l'éligibilité des
demandes ouvertes et à la vérification de couverture avant l'envoi.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.artisan import ArtisanProfile
from app.models.enums import (
    ArtisanVerifiedStatus,
    EngagementBlocker,
)
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import requests as requests_repository
from app.repositories import trades as trades_repository
from app.repositories.requests import location_to_lat_lng
from app.schemas.interventions import (
    EngagementCheckOut,
    RequestEligibilityOut,
)
from app.services import requests as requests_service
from app.services.artisans import get_artisan_or_404
from app.services.requests import MetierInconnuError
from app.services.verification import compute_verified_status


async def evaluate_engagement(
    session: AsyncSession,
    *,
    artisan: ArtisanProfile,
    trade_id: uuid.UUID,
    lat: float,
    lng: float,
    settings: Settings,
) -> EngagementBlocker | None:
    """La règle d'engagement côté artisan, SOURCE UNIQUE (règles 3 à 5 de
    `create_intervention`) : artisan vérifié, métier exercé, zone
    d'intervention (`service_area`, sinon `service_radius_m` autour de
    `base_location`) qui couvre le point. Renvoie le premier obstacle, ou
    `None`.

    Utilisée par la création d'intervention (refus) ET par les lectures
    d'éligibilité (marquage avant envoi) : l'écran ne peut jamais annoncer
    « dans sa zone » une demande que le serveur refuserait, ni l'inverse.
    """
    verified_status = compute_verified_status(
        artisan.verifications, settings.verification_required_doc_types
    )
    if verified_status is not ArtisanVerifiedStatus.VERIFIED:
        return EngagementBlocker.ARTISAN_NON_VERIFIE
    if artisan.suspended_at is not None:
        return EngagementBlocker.ARTISAN_INDISPONIBLE
    if not await artisans_repository.artisan_exercises_trade(
        session, artisan_id=artisan.id, trade_id=trade_id
    ):
        return EngagementBlocker.METIER_NON_EXERCE
    if not await artisans_repository.is_artisan_reachable_for_trade(
        session, artisan_id=artisan.id, trade_id=trade_id, lat=lat, lng=lng
    ):
        return EngagementBlocker.HORS_ZONE
    return None


async def list_request_eligibility(
    session: AsyncSession, *, client: User, artisan_id: uuid.UUID, settings: Settings
) -> list[RequestEligibilityOut]:
    """Pour chaque demande OUVERTE du client courant : peut-elle être
    adressée à cet artisan ? Lecture seule, rien n'est créé. Seules les
    demandes du client sont lues (jamais celles d'autrui)."""
    artisan = await get_artisan_or_404(session, artisan_id)
    requests = await requests_repository.list_open_by_client(
        session,
        client.id,
        created_after=requests_service.expiry_cutoff(settings),
        limit=settings.pagination_page_size_max,
    )
    results: list[RequestEligibilityOut] = []
    for request in requests:
        lat, lng = location_to_lat_lng(request)
        blocker = await evaluate_engagement(
            session, artisan=artisan, trade_id=request.trade_id, lat=lat, lng=lng, settings=settings
        )
        results.append(
            RequestEligibilityOut(request_id=request.id, eligible=blocker is None, reason=blocker)
        )
    return results


async def check_coverage(
    session: AsyncSession,
    *,
    artisan_id: uuid.UUID,
    trade_code: str,
    lat: float,
    lng: float,
    settings: Settings,
) -> EngagementCheckOut:
    """Cet artisan peut-il intervenir pour ce métier à ce lieu ? Lecture
    seule, avant même qu'une demande existe (écran de description d'un
    besoin adressé à un artisan) : rien n'est créé ni réservé."""
    artisan = await get_artisan_or_404(session, artisan_id)
    trade = await trades_repository.get_active_trade_by_code(session, trade_code)
    if trade is None:
        raise MetierInconnuError()
    blocker = await evaluate_engagement(
        session, artisan=artisan, trade_id=trade.id, lat=lat, lng=lng, settings=settings
    )
    return EngagementCheckOut(eligible=blocker is None, reason=blocker)
