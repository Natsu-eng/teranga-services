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
from app.models.enums import InterventionStatus, PaymentStatus
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
    """Revenus dérivés des paiements réussis sur les interventions de
    l'artisan. `None` si aucun paiement -- laisse le service décider de la
    valeur d'affichage (BUILD_PLAN.md §5, réservé au propriétaire/admin)."""
    stmt = (
        select(func.sum(Payment.amount_fcfa))
        .select_from(Payment)
        .join(Intervention, Intervention.id == Payment.intervention_id)
        .where(
            Intervention.artisan_id == artisan_id,
            Payment.status == PaymentStatus.REUSSI,
        )
    )
    return (await session.execute(stmt)).scalar_one()
