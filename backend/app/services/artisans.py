"""Logique métier de lecture des artisans (BUILD_PLAN.md §3.2, §5, §6 Lot 9).

Valide les paramètres de recherche (position, rayon, tri, pagination),
assemble les schémas de sortie depuis les entités ORM chargées par le
repository -- jamais l'inverse, le repository ne connaît pas Pydantic.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.full_name import validate_full_name
from app.models.artisan import ArtisanProfile
from app.models.enums import Role, VerificationDocType
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import trades as trades_repository
from app.repositories.artisans import ArtisanSearchFilters, ArtisanSort
from app.repositories.requests import to_point
from app.schemas.artisans import (
    ArtisanDetailOut,
    ArtisanListItemOut,
    ArtisanProfileUpdateIn,
    ArtisanStatsPrivateOut,
    ArtisanStatsPublicOut,
    ArtisanTradeCreateIn,
    ArtisanTradeOut,
)
from app.schemas.pagination import Page
from app.schemas.trades import TradeOut
from app.services.identity import public_display_name
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


class StatistiquesPriveesInterditesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="STATISTIQUES_PRIVEES_INTERDITES",
            message="Vous n'avez pas accès aux statistiques financières de cet artisan.",
            status_code=403,
        )


class ArtisanProfilIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_PROFIL_INTROUVABLE",
            message="Aucun profil artisan n'est associé à ce compte.",
            status_code=404,
        )


class MetierIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="METIER_INTROUVABLE",
            message="Ce métier n'existe pas ou n'est plus actif.",
            status_code=422,
        )


class ArtisanMetierDejaDeclareError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_METIER_DEJA_DECLARE",
            message="Vous exercez déjà ce métier -- retirez-le d'abord pour en changer les"
            " conditions.",
            status_code=409,
        )


class ArtisanTradeIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_TRADE_NOT_FOUND",
            message="Ce métier déclaré est introuvable.",
            status_code=404,
        )


class ZoneInterventionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ZONE_INTERVENTION_INVALIDE",
            message="La zone d'intervention fournie est invalide (le polygone doit être fermé).",
            status_code=422,
        )


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
        "full_name": public_display_name(profile.user.full_name),
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
                id=artisan_trade.id,
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


def to_detail(
    profile: ArtisanProfile, *, required_doc_types: Sequence[VerificationDocType]
) -> ArtisanDetailOut:
    return ArtisanDetailOut(
        **_common_fields(profile, None, required_doc_types=required_doc_types),
        cover_url=profile.cover_url,
        created_at=profile.created_at,
        is_suspended=profile.suspended_at is not None,
    )


async def list_artisans(
    session: AsyncSession,
    *,
    # **Décision produit actée (onboarding artisan) : un artisan dont
    # `verified_status != VERIFIED` est INVISIBLE dans cette recherche
    # publique** -- filtré en SQL par `app.repositories.artisans`, pas de
    # paramètre pour le désactiver. Alternative envisagée : les montrer avec
    # une mention "non vérifié" non contactable. Écartée pour le lancement :
    # (1) exposer publiquement un profil non vérifié (nom, bio, avis
    #     inexistants puisqu'aucune intervention n'a pu être complétée)
    #     n'apporte aucune valeur à un client qui ne pourra de toute façon
    #     pas le contacter (`create_intervention` rejette déjà
    #     `ARTISAN_NON_VERIFIE`) -- juste de la confusion et des demandes
    #     mort-nées ;
    # (2) un catalogue 100 % vérifié au lancement est un signal de confiance
    #     plus fort qu'un catalogue mêlant vérifié/non vérifié, dans un
    #     marché (artisanat, paiements en espèces) où la confiance est déjà
    #     le principal frein identifié (BUILD_PLAN.md §7, anti-fuite) ;
    # (3) ça ne bloque pas l'artisan : `GET /artisans/{id}` (son propre
    #     profil, onboarding) et `GET /artisans/{id}/stats` restent
    #     accessibles à l'artisan lui-même quel que soit son statut -- seule
    #     la recherche *publique* est concernée.
    # Revisitable plus tard (ex. si le volume d'artisans vérifiés est trop
    # faible pour un catalogue crédible), mais pas au lancement.
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
    session: AsyncSession,
    artisan_id: uuid.UUID,
    *,
    settings: Settings,
    requester: User | None = None,
) -> ArtisanDetailOut:
    """Fiche d'un artisan. Suspendu : servie seulement à lui-même et aux
    admins -- pour le public, il n'existe plus (même 404 qu'un id inconnu)."""
    profile = await get_artisan_or_404(session, artisan_id)
    if profile.suspended_at is not None and (
        requester is None or not _is_owner_or_admin(profile, requester)
    ):
        raise ArtisanIntrouvableError()
    required_doc_types = list(settings.verification_required_doc_types)
    return to_detail(profile, required_doc_types=required_doc_types)


def _is_owner_or_admin(profile: ArtisanProfile, requester: User) -> bool:
    return requester.role is Role.ADMIN or profile.user_id == requester.id


async def get_stats(
    session: AsyncSession, *, artisan_id: uuid.UUID, requester: User | None
) -> ArtisanStatsPublicOut | ArtisanStatsPrivateOut:
    """Statistiques d'un artisan (BUILD_PLAN.md §5, §6 Lot 9).

    - Anonyme : indicateurs de réputation seulement (200), aucun champ
      financier dans la réponse.
    - Propriétaire (artisan dont `artisan_profile.user_id == requester.id`)
      ou admin : indicateurs + revenus (200).
    - Authentifié mais ni l'un ni l'autre : 403 -- les statistiques
      financières ne sont jamais dégradées silencieusement pour un tiers
      identifié, contrairement à un visiteur anonyme qui ne les a jamais
      demandées.
    """
    profile = await get_artisan_or_404(session, artisan_id)
    interventions_count = await artisans_repository.count_completed_interventions(
        session, artisan_id
    )
    public = ArtisanStatsPublicOut(
        rating_avg=float(profile.rating_avg) if profile.rating_avg is not None else None,
        review_count=profile.review_count,
        interventions_count=interventions_count,
        response_rate=None,
    )

    if requester is None:
        return public
    if _is_owner_or_admin(profile, requester):
        revenue_fcfa = await artisans_repository.sum_revenue_fcfa(session, artisan_id)
        return ArtisanStatsPrivateOut(**public.model_dump(), revenue_fcfa=revenue_fcfa or 0)
    raise StatistiquesPriveesInterditesError()


async def get_own_profile(session: AsyncSession, user: User) -> ArtisanProfile:
    """Résout le `artisan_profile` de l'utilisateur courant depuis `user.id`
    (JWT) -- jamais un id reçu du client. Réutilisé par `update_profile`,
    les métiers déclarés et `app.services.documents`."""
    artisan_id = await artisans_repository.get_artisan_profile_id_by_user_id(session, user.id)
    if artisan_id is None:
        raise ArtisanProfilIntrouvableError()
    return await get_artisan_or_404(session, artisan_id)


async def update_profile(
    session: AsyncSession, *, user: User, payload: ArtisanProfileUpdateIn, settings: Settings
) -> ArtisanDetailOut:
    """`PATCH /artisans/me` (BUILD_PLAN.md §3.2, onboarding artisan) : édite
    le `artisan_profile` de l'utilisateur courant -- jamais celui d'un tiers.

    Mise à jour partielle : seuls les champs réellement présents dans le
    JSON (`exclude_unset`) sont appliqués, pour que ce même endpoint serve
    aussi bien le toggle historique (`{is_available}` seul, Lot 12c) que
    l'édition complète de l'onboarding, sans qu'omettre un champ ne
    l'efface. Ne touche jamais `verified_status` (toujours dérivé) ni le
    rôle -- absents du schéma d'entrée."""
    profile = await get_own_profile(session, user)
    fields = payload.model_dump(exclude_unset=True)

    if "is_available" in fields:
        profile.is_available = fields["is_available"]
    if fields.get("full_name") is not None:
        # Vit sur `user`, pas sur `artisan_profile` -- `profile.user` est
        # déjà eager-loadé par `get_own_profile` (pas de requête N+1). Un
        # `full_name: null` explicite est ignoré plutôt que rejeté : la
        # colonne est NOT NULL, il n'existe pas de "nom effacé" valide.
        profile.user.full_name = validate_full_name(fields["full_name"])
    if "bio" in fields:
        profile.bio = fields["bio"]
    if "years_experience" in fields:
        profile.years_experience = fields["years_experience"]
    if "avatar_url" in fields:
        profile.avatar_url = fields["avatar_url"]
    if "cover_url" in fields:
        profile.cover_url = fields["cover_url"]
    if "base_location" in fields:
        location = fields["base_location"]
        profile.base_location = to_point(lat=location["lat"], lng=location["lng"])

    await session.flush()
    required_doc_types = list(settings.verification_required_doc_types)
    return to_detail(profile, required_doc_types=required_doc_types)


def _to_polygon(points: Sequence[Any]) -> WKTElement:
    """Convertit une liste de points (`LocationIn`) en `geography(Polygon)` --
    exige un anneau fermé (premier point == dernier point), même convention
    que `tests/factories.bounding_box_polygon`."""
    first, last = points[0], points[-1]
    if (first.lat, first.lng) != (last.lat, last.lng):
        raise ZoneInterventionInvalideError()
    coords = ", ".join(f"{p.lng} {p.lat}" for p in points)
    return WKTElement(f"POLYGON(({coords}))", srid=4326)


async def add_trade(
    session: AsyncSession, *, user: User, payload: ArtisanTradeCreateIn, settings: Settings
) -> ArtisanDetailOut:
    """`POST /artisans/me/trades` (BUILD_PLAN.md §3.2, onboarding artisan) :
    déclare un métier exercé par l'artisan courant, avec son tarif indicatif
    et sa zone d'intervention (rayon, ou polygone précis optionnel)."""
    profile = await get_own_profile(session, user)

    trade = await trades_repository.get_active_trade_by_code(session, payload.trade_code)
    if trade is None:
        raise MetierIntrouvableError()

    if await artisans_repository.artisan_exercises_trade(
        session, artisan_id=profile.id, trade_id=trade.id
    ):
        raise ArtisanMetierDejaDeclareError()

    service_area = _to_polygon(payload.service_area) if payload.service_area else None
    await artisans_repository.create_artisan_trade(
        session,
        artisan=profile,
        trade_id=trade.id,
        hourly_rate_fcfa=payload.hourly_rate_fcfa,
        service_radius_m=payload.service_radius_m,
        service_area=service_area,
    )

    required_doc_types = list(settings.verification_required_doc_types)
    return to_detail(profile, required_doc_types=required_doc_types)


async def remove_trade(
    session: AsyncSession, *, user: User, artisan_trade_id: uuid.UUID, settings: Settings
) -> ArtisanDetailOut:
    """`DELETE /artisans/me/trades/{id}` (BUILD_PLAN.md §3.2, onboarding
    artisan) : retire un métier déclaré par l'artisan courant -- jamais
    celui d'un tiers (scopé par `artisan_id`, résolu depuis le token)."""
    profile = await get_own_profile(session, user)
    artisan_trade = await artisans_repository.get_owned_artisan_trade(
        session, artisan_trade_id=artisan_trade_id, artisan_id=profile.id
    )
    if artisan_trade is None:
        raise ArtisanTradeIntrouvableError()

    await artisans_repository.delete_artisan_trade(
        session, artisan=profile, artisan_trade=artisan_trade
    )

    required_doc_types = list(settings.verification_required_doc_types)
    return to_detail(profile, required_doc_types=required_doc_types)
