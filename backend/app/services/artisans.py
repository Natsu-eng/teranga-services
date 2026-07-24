"""Logique métier de lecture des artisans (BUILD_PLAN.md §3.2, §5, §6 Lot 9).

Valide les paramètres de recherche (position, rayon, tri, pagination),
assemble les schémas de sortie depuis les entités ORM chargées par le
repository -- jamais l'inverse, le repository ne connaît pas Pydantic.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile
from app.models.enums import VerificationDocType
from app.repositories import artisans as artisans_repository
from app.repositories.artisans import ArtisanSearchFilters, ArtisanSort
from app.schemas.artisans import ArtisanDetailOut, ArtisanListItemOut, ArtisanTradeOut
from app.schemas.pagination import Page
from app.schemas.trades import TradeOut
from app.services.verification import compute_verified_status


class PositionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="POSITION_INVALIDE",
            message="La position fournie (near) est invalide. Format attendu : lat,lng.",
            status_code=422,
        )


class RayonRechercheInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="RAYON_RECHERCHE_INVALIDE",
            message="Le rayon de recherche demandé est invalide ou dépasse le maximum autorisé.",
            status_code=422,
        )


class TriDistanceSansPositionError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TRI_DISTANCE_SANS_POSITION",
            message="Le tri par distance (sort=distance) nécessite une position (near).",
            status_code=422,
        )


class PageHorsBornesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAGE_HORS_BORNES",
            message="Le numéro de page demandé dépasse le maximum autorisé.",
            status_code=422,
        )


class ArtisanIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(code="ARTISAN_NOT_FOUND", message="Artisan introuvable.", status_code=404)


def _parse_near(raw: str) -> tuple[float, float]:
    parts = raw.split(",")
    if len(parts) != 2:
        raise PositionInvalideError()
    try:
        lat, lng = float(parts[0].strip()), float(parts[1].strip())
    except ValueError as exc:
        raise PositionInvalideError() from exc
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise PositionInvalideError()
    return lat, lng


def _resolve_sort(sort: ArtisanSort | None, near: tuple[float, float] | None) -> ArtisanSort:
    if sort == "distance" and near is None:
        raise TriDistanceSansPositionError()
    if sort is not None:
        return sort
    return "distance" if near is not None else "rating"


def _resolve_radius(
    radius_m: int | None, near: tuple[float, float] | None, settings: Settings
) -> int:
    if near is None:
        return 0  # n'a de sens que si `near` est fourni, ignoré par le repository sinon
    value = radius_m if radius_m is not None else settings.artisan_search_default_radius_m
    if value <= 0 or value > settings.artisan_search_max_radius_m:
        raise RayonRechercheInvalideError()
    return value


def _common_fields(
    profile: ArtisanProfile,
    distance_m: int | None,
    *,
    required_doc_types: Sequence[VerificationDocType],
) -> dict[str, Any]:
    """Champs partagés entre `ArtisanListItemOut` et `ArtisanDetailOut`.

    Jamais de coordonnées brutes ni de contact (BUILD_PLAN.md §2.2) : seule
    `distance_m` porte un signal de position, uniquement quand `near` a été
    fourni à la recherche.
    """
    return {
        "id": profile.id,
        "full_name": profile.user.full_name,
        "avatar_url": profile.avatar_url,
        "bio": profile.bio,
        "years_experience": profile.years_experience,
        "is_available": profile.is_available,
        "verified_status": compute_verified_status(profile.verifications, required_doc_types),
        "subscription_tier": profile.subscription_tier,
        "rating_avg": float(profile.rating_avg) if profile.rating_avg is not None else None,
        "review_count": profile.review_count,
        "distance_m": distance_m,
        "trades": [
            ArtisanTradeOut(
                trade=TradeOut.model_validate(artisan_trade.trade),
                hourly_rate_fcfa=artisan_trade.hourly_rate_fcfa,
                service_radius_m=artisan_trade.service_radius_m,
                has_custom_service_area=artisan_trade.service_area is not None,
            )
            for artisan_trade in profile.artisan_trades
        ],
    }


def _to_list_item(
    profile: ArtisanProfile,
    distance_m: int | None,
    *,
    required_doc_types: Sequence[VerificationDocType],
) -> ArtisanListItemOut:
    return ArtisanListItemOut(
        **_common_fields(profile, distance_m, required_doc_types=required_doc_types)
    )


def _to_detail(
    profile: ArtisanProfile, *, required_doc_types: Sequence[VerificationDocType]
) -> ArtisanDetailOut:
    return ArtisanDetailOut(
        **_common_fields(profile, None, required_doc_types=required_doc_types),
        cover_url=profile.cover_url,
        created_at=profile.created_at,
    )


async def list_artisans(
    session: AsyncSession,
    *,
    trade: str | None,
    near: str | None,
    radius_m: int | None,
    min_rating: float | None,
    available: bool | None,
    q: str | None,
    sort: ArtisanSort | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[ArtisanListItemOut]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)

    parsed_near = _parse_near(near) if near is not None else None
    resolved_sort = _resolve_sort(sort, parsed_near)
    resolved_radius = _resolve_radius(radius_m, parsed_near, settings)

    filters = ArtisanSearchFilters(
        trade_code=trade,
        near=parsed_near,
        radius_m=resolved_radius,
        min_rating=Decimal(str(min_rating)) if min_rating is not None else None,
        available=available,
        q=q,
        sort=resolved_sort,
    )
    offset = (page - 1) * resolved_page_size

    # Jamais en parallèle (asyncio.gather) : une AsyncSession n'est pas
    # ré-entrante, deux requêtes concurrentes sur la même connexion lèveraient
    # une erreur ou corrompraient l'état de la transaction.
    rows = await artisans_repository.search_artisans(
        session, filters, limit=resolved_page_size, offset=offset
    )
    total = await artisans_repository.count_artisans(session, filters)

    required_doc_types = list(settings.verification_required_doc_types)
    items = [
        _to_list_item(profile, distance, required_doc_types=required_doc_types)
        for profile, distance in rows
    ]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)


async def get_artisan_or_404(session: AsyncSession, artisan_id: uuid.UUID) -> ArtisanProfile:
    profile = await artisans_repository.get_artisan_by_id(session, artisan_id)
    if profile is None:
        raise ArtisanIntrouvableError()
    return profile


async def get_artisan_detail(
    session: AsyncSession, artisan_id: uuid.UUID, *, settings: Settings
) -> ArtisanDetailOut:
    profile = await get_artisan_or_404(session, artisan_id)
    required_doc_types = list(settings.verification_required_doc_types)
    return _to_detail(profile, required_doc_types=required_doc_types)
