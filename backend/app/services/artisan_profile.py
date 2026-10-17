"""Profil de l'artisan CONNECTÉ (BUILD_PLAN.md onboarding) : résolution de
son profil depuis le jeton (jamais un id reçu du client), mise à jour, ajout
et retrait de métiers. Extraits de `app.services.artisans` sans changement
de logique.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.full_name import validate_full_name
from app.models.artisan import ArtisanProfile
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import trades as trades_repository
from app.repositories.requests import to_point
from app.schemas.artisans import (
    ArtisanDetailOut,
    ArtisanProfileUpdateIn,
    ArtisanTradeCreateIn,
)
from app.services.artisan_errors import (
    ArtisanMetierDejaDeclareError,
    ArtisanProfilIntrouvableError,
    ArtisanTradeIntrouvableError,
    MetierIntrouvableError,
    ZoneInterventionInvalideError,
)
from app.services.artisans import (
    get_artisan_or_404,
    to_detail,
)


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
