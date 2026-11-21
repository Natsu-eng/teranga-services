"""Zone d'intervention de l'artisan connecté : position, rayon par métier,
limites de changement et journal d'audit.

Règles :
- Une position n'est jamais précise : centre officiel d'un quartier de la
  liste fermée, ou position GPS (dans la région desservie) arrondie sur la
  grille ARTISAN_GPS_GRID_M avant d'être enregistrée.
- Chaque changement (position ou rayon d'un métier) est journalisé
  (`artisan.location_change`) SANS aucune coordonnée : source, quartier,
  rayons seulement.
- Limites : ARTISAN_LOCATION_CHANGES_SHORT_MAX par fenêtre courte et
  ARTISAN_LOCATION_CHANGES_LONG_MAX par fenêtre longue, comptées dans le
  journal (une fenêtre de 30 jours dépasse ce que garde le limiteur de
  débit). Tant que l'artisan n'est pas placé, rien ne compte : le premier
  placement est gratuit, comme les réglages de rayon pendant l'inscription.
- La ligne du profil est verrouillée pendant la vérification : deux
  demandes simultanées ne peuvent pas dépasser la limite ensemble.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import Settings
from app.core.geo_privacy import haversine_m, snap_to_grid
from app.core.neighborhoods import DEPARTMENT_LABELS, resolve_neighborhood
from app.models.artisan import ArtisanProfile, ArtisanTrade
from app.models.enums import ArtisanLocationSource, AuditAction, AuditTargetType
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import audit as audit_repository
from app.repositories.requests import to_point
from app.schemas.artisans import (
    ArtisanZoneOut,
    GpsLocationIn,
    NeighborhoodLocationIn,
    ZoneNeighborhoodOut,
    ZoneTradeOut,
)
from app.schemas.trades import TradeOut
from app.services import audit as audit_service
from app.services.artisan_errors import (
    ArtisanTradeIntrouvableError,
    HorsRegionDesservieError,
    QuartierInconnuError,
    RayonInterventionTropGrandError,
    TropDeChangementsDeZoneError,
)


@dataclass(frozen=True)
class ChangeBudget:
    """Changements de zone encore possibles, et quand un redevient possible."""

    remaining_short: int
    remaining_long: int
    next_change_at: datetime | None
    # Fenêtre qui bloque (pour le message), si aucun changement n'est possible.
    blocking_max: int | None = None
    blocking_window_label: str | None = None


def _short_window(settings: Settings) -> timedelta:
    return timedelta(hours=settings.artisan_location_changes_short_window_hours)


def _long_window(settings: Settings) -> timedelta:
    return timedelta(days=settings.artisan_location_changes_long_window_days)


def _next_allowed(dates: list[datetime], *, max_changes: int, window: timedelta) -> datetime:
    """Quand assez de changements seront sortis de la fenêtre pour en
    permettre un nouveau (`dates` triées, au moins `max_changes`)."""
    return dates[len(dates) - max_changes] + window


async def compute_budget(
    session: AsyncSession, artisan_id: uuid.UUID, *, settings: Settings
) -> ChangeBudget:
    now = datetime.now(UTC)
    long_dates = await audit_repository.list_counted_location_changes_since(
        session, artisan_id, since=now - _long_window(settings)
    )
    short_dates = [d for d in long_dates if d >= now - _short_window(settings)]
    short_max = settings.artisan_location_changes_short_max
    long_max = settings.artisan_location_changes_long_max
    remaining_short = max(0, short_max - len(short_dates))
    remaining_long = max(0, long_max - len(long_dates))
    if remaining_short and remaining_long:
        return ChangeBudget(remaining_short, remaining_long, None)

    # Bloqué : la date de reprise est la plus tardive des deux fenêtres.
    candidates: list[tuple[datetime, int, str]] = []
    if not remaining_short:
        candidates.append(
            (
                _next_allowed(short_dates, max_changes=short_max, window=_short_window(settings)),
                short_max,
                f"{settings.artisan_location_changes_short_window_hours} h",
            )
        )
    if not remaining_long:
        candidates.append(
            (
                _next_allowed(long_dates, max_changes=long_max, window=_long_window(settings)),
                long_max,
                f"{settings.artisan_location_changes_long_window_days} jours",
            )
        )
    next_at, blocking_max, label = max(candidates, key=lambda c: c[0])
    return ChangeBudget(remaining_short, remaining_long, next_at, blocking_max, label)


async def _enforce_budget(
    session: AsyncSession, artisan_id: uuid.UUID, *, settings: Settings
) -> None:
    budget = await compute_budget(session, artisan_id, settings=settings)
    if budget.next_change_at is not None:
        assert budget.blocking_max is not None and budget.blocking_window_label is not None
        raise TropDeChangementsDeZoneError(
            max_changes=budget.blocking_max,
            window_label=budget.blocking_window_label,
            retry_at_label=budget.next_change_at.strftime("%d/%m/%Y à %H:%M (UTC)"),
        )


async def _lock_profile(session: AsyncSession, profile_id: uuid.UUID) -> ArtisanProfile:
    """Verrouille la ligne du profil jusqu'à la fin de la transaction et la
    relit (valeurs à jour une fois le verrou obtenu, métiers compris)."""
    stmt = (
        select(ArtisanProfile)
        .where(ArtisanProfile.id == profile_id)
        .options(
            joinedload(ArtisanProfile.user),
            selectinload(ArtisanProfile.artisan_trades).joinedload(ArtisanTrade.trade),
            selectinload(ArtisanProfile.verifications),
        )
        .with_for_update(of=ArtisanProfile)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def _current_point(session: AsyncSession, profile_id: uuid.UUID) -> tuple[float, float]:
    geometry = cast(ArtisanProfile.base_location, Geometry)
    row = (
        await session.execute(
            select(ST_Y(geometry), ST_X(geometry)).where(ArtisanProfile.id == profile_id)
        )
    ).one()
    return float(row[0]), float(row[1])


def _radii(profile: ArtisanProfile) -> list[dict[str, Any]]:
    return sorted(
        (
            {"trade_code": t.trade.code, "radius_m": t.service_radius_m}
            for t in profile.artisan_trades
        ),
        key=lambda item: str(item["trade_code"]),
    )


async def apply_location(
    session: AsyncSession,
    *,
    user: User,
    profile: ArtisanProfile,
    location: NeighborhoodLocationIn | GpsLocationIn,
    settings: Settings,
) -> None:
    """Place l'artisan (quartier ou GPS). Rien n'est enregistré ni compté si
    la position retenue ne change pas."""
    if isinstance(location, NeighborhoodLocationIn):
        neighborhood = resolve_neighborhood(location.neighborhood_id)
        if neighborhood is None:
            raise QuartierInconnuError()
        new_source = ArtisanLocationSource.NEIGHBORHOOD
        new_neighborhood_id: str | None = neighborhood.id
        new_lat, new_lng = neighborhood.lat, neighborhood.lng
    else:
        distance = haversine_m(
            settings.service_region_center_lat,
            settings.service_region_center_lng,
            location.lat,
            location.lng,
        )
        if distance > settings.service_region_radius_m:
            raise HorsRegionDesservieError()
        new_source = ArtisanLocationSource.GPS
        new_neighborhood_id = None
        new_lat, new_lng = snap_to_grid(
            location.lat,
            location.lng,
            grid_m=settings.artisan_gps_grid_m,
            reference_lat=settings.service_region_center_lat,
        )

    profile = await _lock_profile(session, profile.id)
    first_placement = profile.base_location is None
    if not first_placement:
        same_place = (
            profile.location_source == new_source
            and profile.neighborhood_id == new_neighborhood_id
            and await _current_point(session, profile.id) == (new_lat, new_lng)
        )
        if same_place:
            return
        await _enforce_budget(session, profile.id, settings=settings)

    old_source, old_neighborhood_id = profile.location_source, profile.neighborhood_id
    profile.base_location = to_point(lat=new_lat, lng=new_lng)
    profile.location_source = new_source
    profile.neighborhood_id = new_neighborhood_id
    await session.flush()
    await audit_service.record(
        session,
        actor=user,
        action=AuditAction.ARTISAN_LOCATION_CHANGE,
        target_type=AuditTargetType.ARTISAN,
        target_id=profile.id,
        details={
            "kind": "position",
            "counted": not first_placement,
            "first_placement": first_placement,
            "old_source": old_source,
            "new_source": new_source,
            "old_neighborhood_id": old_neighborhood_id,
            "new_neighborhood_id": new_neighborhood_id,
            "radii": _radii(profile),
        },
    )


def ensure_radius_allowed(radius_m: int, *, settings: Settings) -> None:
    if radius_m > settings.artisan_service_radius_max_m:
        raise RayonInterventionTropGrandError(settings.artisan_service_radius_max_m)


async def update_trade_radius(
    session: AsyncSession,
    *,
    user: User,
    profile: ArtisanProfile,
    artisan_trade_id: uuid.UUID,
    radius_m: int,
    settings: Settings,
) -> None:
    """Change le rayon d'UN métier sans le retirer. Compte comme un
    changement de zone dès que l'artisan est placé."""
    ensure_radius_allowed(radius_m, settings=settings)
    profile = await _lock_profile(session, profile.id)
    artisan_trade = await artisans_repository.get_owned_artisan_trade(
        session, artisan_trade_id=artisan_trade_id, artisan_id=profile.id
    )
    if artisan_trade is None:
        raise ArtisanTradeIntrouvableError()
    if artisan_trade.service_radius_m == radius_m:
        return
    placed = profile.base_location is not None
    if placed:
        await _enforce_budget(session, profile.id, settings=settings)

    old_radius = artisan_trade.service_radius_m
    artisan_trade.service_radius_m = radius_m
    await session.flush()
    await audit_service.record(
        session,
        actor=user,
        action=AuditAction.ARTISAN_LOCATION_CHANGE,
        target_type=AuditTargetType.ARTISAN,
        target_id=profile.id,
        details={
            "kind": "radius",
            "counted": placed,
            "first_placement": False,
            "source": profile.location_source,
            "neighborhood_id": profile.neighborhood_id,
            "trade_code": artisan_trade.trade.code,
            "old_radius_m": old_radius,
            "new_radius_m": radius_m,
        },
    )


def _trade_out(artisan_trade: ArtisanTrade) -> ZoneTradeOut:
    return ZoneTradeOut(
        id=artisan_trade.id,
        trade=TradeOut.model_validate(artisan_trade.trade),
        service_radius_m=artisan_trade.service_radius_m,
        has_custom_service_area=artisan_trade.service_area is not None,
    )


async def get_zone(
    session: AsyncSession, *, profile: ArtisanProfile, settings: Settings
) -> ArtisanZoneOut:
    budget = await compute_budget(session, profile.id, settings=settings)
    neighborhood = (
        resolve_neighborhood(profile.neighborhood_id) if profile.neighborhood_id else None
    )
    return ArtisanZoneOut(
        placed=profile.base_location is not None,
        source=profile.location_source,
        neighborhood=(
            ZoneNeighborhoodOut(
                id=neighborhood.id,
                label=neighborhood.label,
                department_label=DEPARTMENT_LABELS[neighborhood.department],
            )
            if neighborhood is not None
            else None
        ),
        trades=[
            _trade_out(t) for t in sorted(profile.artisan_trades, key=lambda t: t.trade.label_fr)
        ],
        radius_max_m=settings.artisan_service_radius_max_m,
        gps_grid_m=settings.artisan_gps_grid_m,
        changes_remaining_short=budget.remaining_short,
        changes_remaining_long=budget.remaining_long,
        short_window_hours=settings.artisan_location_changes_short_window_hours,
        long_window_days=settings.artisan_location_changes_long_window_days,
        next_change_at=budget.next_change_at,
    )
