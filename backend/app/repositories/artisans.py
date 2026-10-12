"""Accès données pour la recherche et la lecture des artisans (BUILD_PLAN.md §5, §6 Lot 9).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation) -- voir `app.services.artisans` pour ça.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_Covers, ST_Distance, ST_DWithin
from sqlalchemy import (
    ColumnElement,
    Integer,
    Numeric,
    Select,
    and_,
    cast,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, joinedload, selectinload

from app.models.artisan import ArtisanProfile, ArtisanTrade
from app.models.enums import ArtisanVerifiedStatus, InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.models.payment import Payment
from app.models.trade import Trade
from app.models.user import User

ArtisanSort = Literal["distance", "rating", "recent"]


@dataclass(frozen=True)
class ArtisanSearchFilters:
    trade_code: str | None = None
    near: tuple[float, float] | None = None  # (lat, lng), déjà validé par le service
    radius_m: int = 0  # n'a de sens que si `near` est fourni
    min_rating: Decimal | None = None
    available: bool | None = None
    q: str | None = None
    sort: ArtisanSort = "rating"


def _to_point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def _artisan_trade_reachable(
    filters: ArtisanSearchFilters, point: WKTElement | None
) -> ColumnElement[bool]:
    """EXISTS corrélé : l'artisan exerce (le) métier demandé, ET, si une
    position est fournie, sa zone d'intervention (`service_area` si définie,
    sinon `service_radius_m` autour de `base_location`) couvre ce point.

    Systématique (même sans `trade`/`near` actifs) : un artisan sans aucun
    `artisan_trade` n'apparaît jamais dans une recherche.
    """
    conditions: list[ColumnElement[bool]] = [ArtisanTrade.artisan_id == ArtisanProfile.id]
    if filters.trade_code is not None:
        conditions.append(
            ArtisanTrade.trade_id.in_(select(Trade.id).where(Trade.code == filters.trade_code))
        )
    if point is not None:
        conditions.append(
            or_(
                and_(
                    ArtisanTrade.service_area.is_not(None),
                    ST_Covers(ArtisanTrade.service_area, point),
                ),
                and_(
                    ArtisanTrade.service_area.is_(None),
                    ST_DWithin(ArtisanProfile.base_location, point, ArtisanTrade.service_radius_m),
                ),
            )
        )
    return select(ArtisanTrade.id).where(*conditions).exists()


def _user_active(user_id_column: InstrumentedAttribute[uuid.UUID]) -> ColumnElement[bool]:
    return exists(select(User.id).where(User.id == user_id_column, User.deleted_at.is_(None)))


def _build_filtered_query(
    filters: ArtisanSearchFilters,
) -> tuple[Select[tuple[ArtisanProfile]], WKTElement | None]:
    point = _to_point(*filters.near) if filters.near is not None else None

    stmt: Select[tuple[ArtisanProfile]] = select(ArtisanProfile).where(
        ArtisanProfile.deleted_at.is_(None),
        _user_active(ArtisanProfile.user_id),
        # Un artisan non vérifié n'apparaît jamais dans la recherche
        # publique (BUILD_PLAN.md, onboarding artisan -- décision actée :
        # ne montrer que du vérifié au lancement, cf. commentaire détaillé
        # dans app.services.artisans.list_artisans). Repose sur la colonne
        # stockée (pas un recalcul par ligne) : tenue à jour à chaque
        # écriture de `verification` (app.services.documents) et par le
        # futur lot de vérification admin -- jamais lue ainsi pour la
        # *sortie* API (`verified_status` reste recalculé à la volée),
        # seulement comme filtre de visibilité.
        ArtisanProfile.verified_status == ArtisanVerifiedStatus.VERIFIED,
        # Suspendu par un admin : invisible, quelle que soit sa vérification.
        ArtisanProfile.suspended_at.is_(None),
        _artisan_trade_reachable(filters, point),
    )
    if point is not None:
        stmt = stmt.where(ST_DWithin(ArtisanProfile.base_location, point, filters.radius_m))
    if filters.min_rating is not None:
        stmt = stmt.where(ArtisanProfile.rating_avg >= filters.min_rating)
    if filters.available is not None:
        stmt = stmt.where(ArtisanProfile.is_available.is_(filters.available))
    if filters.q:
        pattern = f"%{filters.q}%"
        full_name = (
            select(User.full_name).where(User.id == ArtisanProfile.user_id).scalar_subquery()
        )
        stmt = stmt.where(or_(full_name.ilike(pattern), ArtisanProfile.bio.ilike(pattern)))

    return stmt, point


def _eager_load(stmt: Select[tuple[ArtisanProfile]]) -> Select[tuple[ArtisanProfile]]:
    return stmt.options(
        joinedload(ArtisanProfile.user),
        selectinload(ArtisanProfile.artisan_trades).joinedload(ArtisanTrade.trade),
        selectinload(ArtisanProfile.verifications),
    )


def _apply_sort(
    stmt: Select[tuple[ArtisanProfile]], filters: ArtisanSearchFilters, point: WKTElement | None
) -> Select[tuple[ArtisanProfile]]:
    # Tie-breaker `id` systématique : sans lui, un tri sur des valeurs égales
    # (plusieurs artisans à rating_avg=5.00, ou créés à la même seconde) n'est
    # pas déterministe entre deux pages -- un artisan pourrait apparaître deux
    # fois ou jamais selon le plan d'exécution Postgres.
    if filters.sort == "distance":
        assert point is not None  # garanti par le service (TriDistanceSansPositionError sinon)
        return stmt.order_by(ST_Distance(ArtisanProfile.base_location, point), ArtisanProfile.id)
    if filters.sort == "recent":
        return stmt.order_by(ArtisanProfile.created_at.desc(), ArtisanProfile.id)
    # "rating" : NULLS LAST explicite -- Postgres met les NULL en tête en DESC
    # par défaut, ce qui remonterait les artisans jamais notés en tête.
    return stmt.order_by(ArtisanProfile.rating_avg.desc().nulls_last(), ArtisanProfile.id)


async def search_artisans(
    session: AsyncSession, filters: ArtisanSearchFilters, *, limit: int, offset: int
) -> list[tuple[ArtisanProfile, int | None]]:
    stmt, point = _build_filtered_query(filters)
    stmt = _eager_load(stmt)
    stmt = _apply_sort(stmt, filters, point)
    stmt = stmt.limit(limit).offset(offset)

    if point is None:
        rows = (await session.execute(stmt)).unique().scalars().all()
        return [(profile, None) for profile in rows]

    distance_numeric = cast(ST_Distance(ArtisanProfile.base_location, point), Numeric)
    distance_m = cast(func.round(distance_numeric), Integer)
    result = await session.execute(stmt.add_columns(distance_m.label("distance_m")))
    return [(row[0], row[1]) for row in result.unique().all()]


async def count_artisans(session: AsyncSession, filters: ArtisanSearchFilters) -> int:
    stmt, _ = _build_filtered_query(filters)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    return (await session.execute(count_stmt)).scalar_one()


async def get_artisan_by_id(session: AsyncSession, artisan_id: uuid.UUID) -> ArtisanProfile | None:
    stmt = _eager_load(
        select(ArtisanProfile).where(
            ArtisanProfile.id == artisan_id,
            ArtisanProfile.deleted_at.is_(None),
            _user_active(ArtisanProfile.user_id),
        )
    )
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def count_completed_interventions(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Intervention)
        .where(
            Intervention.artisan_id == artisan_id,
            Intervention.status == InterventionStatus.TERMINEE,
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def sum_revenue_fcfa(session: AsyncSession, artisan_id: uuid.UUID) -> int | None:
    """Chiffre d'affaires encaissé (montants bruts) sur les interventions de
    l'artisan : séquestre libéré (`libere`) ou espèces réglées directement
    (`reussi`) -- jamais un paiement encore retenu ou remboursé (BUILD_PLAN.md
    §3.5). `None` si aucun paiement -- laisse le service décider de la
    valeur d'affichage (BUILD_PLAN.md §5, réservé au propriétaire/admin)."""
    stmt = (
        select(func.sum(Payment.amount_fcfa))
        .select_from(Payment)
        .join(Intervention, Intervention.id == Payment.intervention_id)
        .where(
            Intervention.artisan_id == artisan_id,
            Payment.status.in_((PaymentStatus.LIBERE, PaymentStatus.REUSSI)),
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def get_artisan_profile_id_by_user_id(
    session: AsyncSession, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Le `artisan_profile.id` d'un `user`, ou `None` s'il n'en a pas (compte
    client, ou artisan sans profil créé). Ferme le lien `user <-> artisan_profile`
    jamais exposé jusqu'ici (AUDIT_PHASE2.md §6, BUILD_PLAN.md §6 Lot 12) --
    utilisé par `GET /auth/me` et par les endpoints `/interventions` pour
    résoudre "l'artisan courant" à partir de l'utilisateur authentifié.
    """
    stmt = select(ArtisanProfile.id).where(
        ArtisanProfile.user_id == user_id, ArtisanProfile.deleted_at.is_(None)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def artisan_exercises_trade(
    session: AsyncSession, *, artisan_id: uuid.UUID, trade_id: uuid.UUID
) -> bool:
    stmt = (
        select(ArtisanTrade.id)
        .where(ArtisanTrade.artisan_id == artisan_id, ArtisanTrade.trade_id == trade_id)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def create_artisan_trade(
    session: AsyncSession,
    *,
    artisan: ArtisanProfile,
    trade_id: uuid.UUID,
    hourly_rate_fcfa: int,
    service_radius_m: int,
    service_area: WKTElement | None,
) -> ArtisanTrade:
    # `artisan=artisan` (pas `artisan_id=artisan.id`) : peuple
    # `ArtisanProfile.artisan_trades` en mémoire immédiatement, sans requête
    # -- même pattern que `app.repositories.verification.create_verification`.
    artisan_trade = ArtisanTrade(
        artisan=artisan,
        trade_id=trade_id,
        hourly_rate_fcfa=hourly_rate_fcfa,
        service_radius_m=service_radius_m,
        service_area=service_area,
    )
    session.add(artisan_trade)
    await session.flush()
    return artisan_trade


async def get_owned_artisan_trade(
    session: AsyncSession, *, artisan_trade_id: uuid.UUID, artisan_id: uuid.UUID
) -> ArtisanTrade | None:
    """Un `artisan_trade`, scopé à l'artisan propriétaire -- `None` si absent
    OU s'il appartient à un autre artisan (jamais de distinction observable
    depuis l'extérieur, cf. `app.services.artisans`)."""
    stmt = select(ArtisanTrade).where(
        ArtisanTrade.id == artisan_trade_id, ArtisanTrade.artisan_id == artisan_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_artisan_trade(
    session: AsyncSession, *, artisan: ArtisanProfile, artisan_trade: ArtisanTrade
) -> None:
    # Retrait via la collection (pas `session.delete(artisan_trade)`
    # directement) : déclenche le cascade `delete-orphan` déjà configuré sur
    # `ArtisanProfile.artisan_trades`, et laisse la collection en mémoire
    # cohérente avec l'état persistant sans requête supplémentaire --
    # important ici puisque `artisan.artisan_trades` est resérialisé juste
    # après par `app.services.artisans.remove_trade`.
    artisan.artisan_trades.remove(artisan_trade)
    await session.flush()


async def is_artisan_reachable_for_trade(
    session: AsyncSession, *, artisan_id: uuid.UUID, trade_id: uuid.UUID, lat: float, lng: float
) -> bool:
    """La zone d'intervention de l'artisan pour ce métier (`service_area` si
    définie, sinon `service_radius_m` autour de `base_location`) couvre-t-elle
    (lat, lng) ? Même règle que la recherche multi-artisans (Lot 9,
    BUILD_PLAN.md §5.1), scopée ici à un artisan et un métier déjà connus --
    utilisée à la création d'une intervention (BUILD_PLAN.md §6 Lot 12) : un
    artisan hors zone ne peut pas être mis en relation sur cette demande.
    """
    target = _to_point(lat, lng)
    stmt = (
        select(ArtisanTrade.id)
        .join(ArtisanProfile, ArtisanProfile.id == ArtisanTrade.artisan_id)
        .where(
            ArtisanTrade.artisan_id == artisan_id,
            ArtisanTrade.trade_id == trade_id,
            or_(
                and_(
                    ArtisanTrade.service_area.is_not(None),
                    ST_Covers(ArtisanTrade.service_area, target),
                ),
                and_(
                    ArtisanTrade.service_area.is_(None),
                    ST_DWithin(ArtisanProfile.base_location, target, ArtisanTrade.service_radius_m),
                ),
            ),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None
