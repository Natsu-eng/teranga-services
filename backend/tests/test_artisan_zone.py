"""Zone d'intervention de l'artisan : placement (quartier ou GPS), limites de
changement, rayon par métier, journal d'audit sans coordonnées, vue admin.

Toutes les valeurs attendues viennent des réglages (`get_settings()`) ou de
la liste des quartiers : rien n'est recopié en dur.
"""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_X, ST_Y
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.geo_privacy import snap_to_grid
from app.core.neighborhoods import LEGACY_ALIASES, resolve_neighborhood
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile, ArtisanTrade
from app.models.audit import AuditLog
from app.models.enums import (
    ArtisanLocationSource,
    AuditAction,
    AuditTargetType,
    Role,
    VerificationDocType,
    VerificationStatus,
)
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_trade,
    make_user,
    make_verification,
)

SETTINGS = get_settings()
# Une position GPS précise à la Médina, choisie hors d'un nœud de la grille.
PRECISE_LAT, PRECISE_LNG = 14.682_731, -17.451_377
# Thiès : hors de la région desservie.
OUTSIDE_LAT, OUTSIDE_LNG = 14.7910, -16.9359


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Generator[None, None, None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.pop(get_session, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _artisan(
    db_session: AsyncSession, *, placed: bool = False
) -> tuple[User, ArtisanProfile]:
    user = await make_user(db_session, role=Role.ARTISAN)
    profile = await make_artisan_profile(db_session, user=user, placed=placed)
    return user, profile


async def _place(user: User, location: dict[str, Any]) -> Response:
    async with _client() as http:
        return await http.patch(
            "/api/v1/artisans/me", json={"location": location}, headers=_auth(user)
        )


def _neighborhood(neighborhood_id: str) -> dict[str, Any]:
    return {"source": "neighborhood", "neighborhood_id": neighborhood_id}


def _gps(lat: float, lng: float) -> dict[str, Any]:
    return {"source": "gps", "lat": lat, "lng": lng}


async def _stored_point(db_session: AsyncSession, profile: ArtisanProfile) -> tuple[float, float]:
    geometry = cast(ArtisanProfile.base_location, Geometry)
    row = (
        await db_session.execute(
            select(ST_Y(geometry), ST_X(geometry)).where(ArtisanProfile.id == profile.id)
        )
    ).one()
    return float(row[0]), float(row[1])


async def _zone(user: User) -> dict[str, Any]:
    async with _client() as http:
        response = await http.get("/api/v1/artisans/me/zone", headers=_auth(user))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _location_changes(db_session: AsyncSession, profile: ArtisanProfile) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.action == AuditAction.ARTISAN_LOCATION_CHANGE,
            AuditLog.target_id == profile.id,
        )
        .order_by(AuditLog.created_at)
    )
    return list((await db_session.execute(stmt)).scalars().all())


# --- Placement ---------------------------------------------------------------


async def test_neighborhood_placement_stores_the_official_center(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    medina = resolve_neighborhood("medina")
    assert medina is not None

    response = await _place(user, _neighborhood("medina"))

    assert response.status_code == 200, response.text
    await db_session.refresh(profile)
    assert profile.location_source == ArtisanLocationSource.NEIGHBORHOOD
    assert profile.neighborhood_id == "medina"
    assert await _stored_point(db_session, profile) == (medina.lat, medina.lng)
    zone = await _zone(user)
    assert zone["placed"] is True
    assert zone["neighborhood"]["label"] == medina.label


@pytest.mark.parametrize("legacy_id", sorted(LEGACY_ALIASES))
async def test_a_legacy_id_is_stored_under_its_current_commune(
    db_session: AsyncSession, legacy_id: str
) -> None:
    user, profile = await _artisan(db_session)

    response = await _place(user, _neighborhood(legacy_id))

    assert response.status_code == 200, response.text
    await db_session.refresh(profile)
    assert profile.neighborhood_id == LEGACY_ALIASES[legacy_id]


async def test_an_unknown_neighborhood_is_refused(db_session: AsyncSession) -> None:
    user, profile = await _artisan(db_session)

    response = await _place(user, _neighborhood("paris-15"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUARTIER_INCONNU"
    await db_session.refresh(profile)
    assert profile.base_location is None


async def test_gps_is_rounded_on_the_grid_before_being_stored(db_session: AsyncSession) -> None:
    user, profile = await _artisan(db_session)

    response = await _place(user, _gps(PRECISE_LAT, PRECISE_LNG))

    assert response.status_code == 200, response.text
    await db_session.refresh(profile)
    expected = snap_to_grid(
        PRECISE_LAT,
        PRECISE_LNG,
        grid_m=SETTINGS.artisan_gps_grid_m,
        reference_lat=SETTINGS.service_region_center_lat,
    )
    stored = await _stored_point(db_session, profile)
    assert stored == expected
    assert stored != (PRECISE_LAT, PRECISE_LNG)
    assert profile.location_source == ArtisanLocationSource.GPS
    assert profile.neighborhood_id is None


async def test_gps_outside_the_served_region_is_refused(db_session: AsyncSession) -> None:
    user, profile = await _artisan(db_session)

    response = await _place(user, _gps(OUTSIDE_LAT, OUTSIDE_LNG))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HORS_REGION_DESSERVIE"
    await db_session.refresh(profile)
    assert profile.base_location is None


@pytest.mark.parametrize("commune_id", ["bargny", "sebikotane", "yene", "tivaouane-peulh-niaga"])
async def test_gps_at_the_farthest_communes_is_accepted(
    db_session: AsyncSession, commune_id: str
) -> None:
    """Les communes les plus éloignées du centre de la région restent
    plaçables par GPS (pas seulement par quartier)."""
    commune = resolve_neighborhood(commune_id)
    assert commune is not None
    user, _ = await _artisan(db_session)

    response = await _place(user, _gps(commune.lat, commune.lng))

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "location",
    [
        # Quartier ET coordonnées : jamais de mélange.
        {"source": "neighborhood", "neighborhood_id": "medina", "lat": 14.68, "lng": -17.45},
        {"source": "gps", "lat": 14.68},
        {"source": "adresse", "text": "Rue 10"},
        None,
    ],
)
async def test_malformed_locations_are_refused(
    db_session: AsyncSession, location: dict[str, Any] | None
) -> None:
    user, profile = await _artisan(db_session)

    response = await _place(user, location)  # type: ignore[arg-type]

    assert response.status_code == 422
    await db_session.refresh(profile)
    assert profile.base_location is None


# --- Limites de changement -----------------------------------------------------


async def test_first_placement_is_free_then_the_short_window_limit_applies(
    db_session: AsyncSession,
) -> None:
    user, _ = await _artisan(db_session)
    short_max = SETTINGS.artisan_location_changes_short_max
    # Communes toutes différentes : chaque appel est un vrai changement.
    communes = ["plateau", "medina", "ouakam", "yoff", "ngor", "hlm", "grand-yoff"]
    assert len(communes) >= short_max + 2

    first = await _place(user, _neighborhood(communes[0]))
    assert first.status_code == 200, first.text
    assert (await _zone(user))["changes_remaining_short"] == short_max

    for commune in communes[1 : short_max + 1]:
        response = await _place(user, _neighborhood(commune))
        assert response.status_code == 200, response.text

    refused = await _place(user, _neighborhood(communes[short_max + 1]))
    assert refused.status_code == 429
    error = refused.json()["error"]
    assert error["code"] == "TROP_DE_CHANGEMENTS_DE_ZONE"
    assert f"{SETTINGS.artisan_location_changes_short_window_hours} h" in error["message"]
    zone = await _zone(user)
    assert zone["changes_remaining_short"] == 0
    assert zone["next_change_at"] is not None
    assert zone["neighborhood"]["id"] == communes[short_max]


async def test_choosing_the_same_place_again_changes_and_counts_nothing(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    await _place(user, _neighborhood("medina"))
    await _place(user, _gps(PRECISE_LAT, PRECISE_LNG))

    again = await _place(user, _gps(PRECISE_LAT + 0.000_01, PRECISE_LNG))

    assert again.status_code == 200
    # Placement initial + un changement : le second GPS (même maille) n'est
    # ni journalisé ni compté.
    assert len(await _location_changes(db_session, profile)) == 2
    assert (await _zone(user))["changes_remaining_short"] == (
        SETTINGS.artisan_location_changes_short_max - 1
    )


async def _journal_past_changes(
    db_session: AsyncSession, user: User, profile: ArtisanProfile, *, count: int, age: timedelta
) -> None:
    for _ in range(count):
        db_session.add(
            AuditLog(
                actor_id=user.id,
                actor_name=user.full_name,
                action=AuditAction.ARTISAN_LOCATION_CHANGE,
                target_type=AuditTargetType.ARTISAN,
                target_id=profile.id,
                details={"kind": "position", "counted": True, "first_placement": False},
                created_at=datetime.now(UTC) - age,
            )
        )
    await db_session.flush()


async def test_the_long_window_limit_applies_beyond_the_short_window(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    await _place(user, _neighborhood("plateau"))
    # Changements anciens : hors fenêtre courte, dans la fenêtre longue.
    age = timedelta(hours=SETTINGS.artisan_location_changes_short_window_hours + 1)
    await _journal_past_changes(
        db_session,
        user,
        profile,
        count=SETTINGS.artisan_location_changes_long_max,
        age=age,
    )

    refused = await _place(user, _neighborhood("medina"))

    assert refused.status_code == 429
    message = refused.json()["error"]["message"]
    assert f"{SETTINGS.artisan_location_changes_long_window_days} jours" in message
    zone = await _zone(user)
    assert zone["changes_remaining_long"] == 0
    assert zone["changes_remaining_short"] == SETTINGS.artisan_location_changes_short_max


async def test_changes_older_than_the_long_window_no_longer_count(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    await _place(user, _neighborhood("plateau"))
    age = timedelta(days=SETTINGS.artisan_location_changes_long_window_days, hours=1)
    await _journal_past_changes(
        db_session,
        user,
        profile,
        count=SETTINGS.artisan_location_changes_long_max,
        age=age,
    )

    response = await _place(user, _neighborhood("medina"))

    assert response.status_code == 200, response.text


# --- Journal d'audit -------------------------------------------------------------


def _numbers_and_keys(value: object) -> tuple[list[str], list[float]]:
    keys: list[str] = []
    floats: list[float] = []
    if isinstance(value, dict):
        for key, item in value.items():
            keys.append(str(key))
            sub_keys, sub_floats = _numbers_and_keys(item)
            keys += sub_keys
            floats += sub_floats
    elif isinstance(value, list):
        for item in value:
            sub_keys, sub_floats = _numbers_and_keys(item)
            keys += sub_keys
            floats += sub_floats
    elif isinstance(value, float):
        floats.append(value)
    return keys, floats


async def test_every_change_is_journaled_without_any_coordinate(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    trade = await make_trade(db_session)
    await make_artisan_trade(db_session, artisan=profile, trade=trade, service_radius_m=8_000)

    await _place(user, _gps(PRECISE_LAT, PRECISE_LNG))
    await _place(user, _neighborhood("medina"))

    first, second = await _location_changes(db_session, profile)
    assert first.actor_id == user.id
    assert first.details["first_placement"] is True
    assert first.details["counted"] is False
    assert first.details["old_source"] is None
    assert first.details["new_source"] == "gps"
    assert second.details["counted"] is True
    assert second.details["old_source"] == "gps"
    assert second.details["new_source"] == "neighborhood"
    assert second.details["new_neighborhood_id"] == "medina"
    assert second.details["radii"] == [{"trade_code": trade.code, "radius_m": 8_000}]
    for entry in (first, second):
        keys, floats = _numbers_and_keys(entry.details)
        assert not any(k in {"lat", "lng", "latitude", "longitude"} for k in keys), keys
        assert floats == [], floats


# --- Rayon par métier --------------------------------------------------------------


async def _patch_radius(user: User, artisan_trade: ArtisanTrade, radius_m: int) -> Response:
    async with _client() as http:
        return await http.patch(
            f"/api/v1/artisans/me/trades/{artisan_trade.id}",
            json={"service_radius_m": radius_m},
            headers=_auth(user),
        )


async def test_the_radius_of_one_trade_changes_without_removing_the_trade(
    db_session: AsyncSession,
) -> None:
    user, profile = await _artisan(db_session)
    await _place(user, _neighborhood("medina"))
    trade = await make_trade(db_session)
    artisan_trade = await make_artisan_trade(
        db_session, artisan=profile, trade=trade, service_radius_m=5_000
    )

    response = await _patch_radius(user, artisan_trade, 12_000)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [t["service_radius_m"] for t in body["trades"]] == [12_000]
    assert body["changes_remaining_short"] == SETTINGS.artisan_location_changes_short_max - 1
    radius_entry = (await _location_changes(db_session, profile))[-1]
    assert radius_entry.details["kind"] == "radius"
    assert radius_entry.details["old_radius_m"] == 5_000
    assert radius_entry.details["new_radius_m"] == 12_000
    assert radius_entry.details["counted"] is True


async def test_a_radius_above_the_cap_is_refused(db_session: AsyncSession) -> None:
    user, profile = await _artisan(db_session)
    trade = await make_trade(db_session)
    artisan_trade = await make_artisan_trade(
        db_session, artisan=profile, trade=trade, service_radius_m=5_000
    )

    response = await _patch_radius(user, artisan_trade, SETTINGS.artisan_service_radius_max_m + 1)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAYON_INTERVENTION_TROP_GRAND"
    await db_session.refresh(artisan_trade)
    assert artisan_trade.service_radius_m == 5_000


async def test_a_new_trade_above_the_radius_cap_is_refused(db_session: AsyncSession) -> None:
    user, _ = await _artisan(db_session)
    trade = await make_trade(db_session)

    async with _client() as http:
        response = await http.post(
            "/api/v1/artisans/me/trades",
            json={
                "trade_code": trade.code,
                "hourly_rate_fcfa": 5_000,
                "service_radius_m": SETTINGS.artisan_service_radius_max_m + 1,
            },
            headers=_auth(user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAYON_INTERVENTION_TROP_GRAND"


async def test_the_radius_of_someone_elses_trade_cannot_be_changed(
    db_session: AsyncSession,
) -> None:
    user, _ = await _artisan(db_session)
    _, other = await _artisan(db_session)
    trade = await make_trade(db_session)
    others_trade = await make_artisan_trade(
        db_session, artisan=other, trade=trade, service_radius_m=5_000
    )

    response = await _patch_radius(user, others_trade, 9_000)

    assert response.status_code == 404
    await db_session.refresh(others_trade)
    assert others_trade.service_radius_m == 5_000


async def test_radius_changes_before_being_placed_do_not_count(db_session: AsyncSession) -> None:
    user, profile = await _artisan(db_session)
    trade = await make_trade(db_session)
    artisan_trade = await make_artisan_trade(
        db_session, artisan=profile, trade=trade, service_radius_m=5_000
    )

    response = await _patch_radius(user, artisan_trade, 7_000)

    assert response.status_code == 200
    assert response.json()["placed"] is False
    assert (await _location_changes(db_session, profile))[-1].details["counted"] is False
    assert response.json()["changes_remaining_short"] == (
        SETTINGS.artisan_location_changes_short_max
    )


# --- Zone et vue admin ------------------------------------------------------------------


async def test_an_unplaced_artisan_sees_that_it_is_placed_nowhere(
    db_session: AsyncSession,
) -> None:
    user, _ = await _artisan(db_session)

    zone = await _zone(user)

    assert zone["placed"] is False
    assert zone["source"] is None
    assert zone["neighborhood"] is None
    assert zone["radius_max_m"] == SETTINGS.artisan_service_radius_max_m


async def test_the_admin_sees_the_zone_and_its_history_without_coordinates(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    user, profile = await _artisan(db_session)
    await _place(user, _neighborhood("medina"))

    async with _client() as http:
        response = await http.get(f"/api/v1/admin/artisans/{profile.id}", headers=_auth(admin))

    assert response.status_code == 200, response.text
    body = response.json()
    medina = resolve_neighborhood("medina")
    assert medina is not None
    assert body["zone"] == {
        "placed": True,
        "source": "neighborhood",
        "neighborhood_id": "medina",
        "neighborhood_label": medina.label,
    }
    assert [e["action"] for e in body["history"]] == ["artisan.location_change"]
    assert "lat" not in str(body["history"]) and "lng" not in str(body["history"])


async def test_the_overview_counts_verified_artisans_placed_nowhere(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)

    async def unplaced() -> int:
        async with _client() as http:
            response = await http.get("/api/v1/admin/overview", headers=_auth(admin))
        assert response.status_code == 200, response.text
        count: int = response.json()["artisans"]["verified_unplaced"]
        return count

    before = await unplaced()
    _, profile = await _artisan(db_session)
    for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
        await make_verification(
            db_session, artisan=profile, doc_type=doc_type, status=VerificationStatus.APPROVED
        )
    # Placé : ne compte pas.
    await _artisan(db_session, placed=True)

    assert await unplaced() == before + 1
