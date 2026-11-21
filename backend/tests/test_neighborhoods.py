"""Liste fermée des quartiers (une entrée par commune de la région de Dakar),
région desservie, calculs de grille et d'arrondi, exposition publique.
"""

import importlib.util
import math
from collections import Counter
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings, get_settings
from app.core.geo_privacy import (
    METERS_PER_DEGREE,
    haversine_m,
    round_public_distance,
    snap_to_grid,
)
from app.core.neighborhoods import (
    DEFAULT_NEIGHBORHOOD_ID,
    LEGACY_ALIASES,
    NEIGHBORHOODS,
    Department,
    resolve_neighborhood,
)
from app.main import app
from app.models.artisan import LOCATION_FIELDS_CONSISTENT_SQL

SETTINGS = get_settings()
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "7c41d2e9a5b3_zone_intervention_artisan.py"
)

# Communes par département (découpage en vigueur, Keur Massar compris) :
# vérifiées une à une dans OpenStreetMap, voir app/core/neighborhoods.py.
EXPECTED_PER_DEPARTMENT = {
    Department.DAKAR: 19,
    Department.PIKINE: 12,
    Department.GUEDIAWAYE: 5,
    Department.KEUR_MASSAR: 6,
    Department.RUFISQUE: 11,
}
# Identifiants historiques gardés par les téléphones des clients.
HISTORICAL_IDS = ("plateau", "almadies", "ouakam", "mermoz-sacre-coeur", "yoff-ngor", "point-e")


def test_one_entry_per_commune_of_the_five_departments() -> None:
    counts = Counter(n.department for n in NEIGHBORHOODS)
    assert counts == EXPECTED_PER_DEPARTMENT
    assert len(NEIGHBORHOODS) == sum(EXPECTED_PER_DEPARTMENT.values()) == 53
    assert len({n.id for n in NEIGHBORHOODS}) == len(NEIGHBORHOODS)
    assert len({n.osm_relation for n in NEIGHBORHOODS}) == len(NEIGHBORHOODS)


@pytest.mark.parametrize(
    "commune_id",
    ["bargny", "sebikotane", "diamniadio", "sangalkam", "bambilor", "yene", "jaxaay-parcelles"],
)
def test_the_outer_communes_named_by_the_product_are_listed(commune_id: str) -> None:
    assert resolve_neighborhood(commune_id) is not None


@pytest.mark.parametrize("historical_id", HISTORICAL_IDS)
def test_every_historical_id_still_resolves(historical_id: str) -> None:
    assert resolve_neighborhood(historical_id) is not None


def test_aliases_point_to_listed_communes_and_never_shadow_one() -> None:
    ids = {n.id for n in NEIGHBORHOODS}
    for alias, target in LEGACY_ALIASES.items():
        assert target in ids
        assert alias not in ids


def test_every_center_is_inside_the_served_region() -> None:
    for n in NEIGHBORHOODS:
        distance = haversine_m(
            SETTINGS.service_region_center_lat, SETTINGS.service_region_center_lng, n.lat, n.lng
        )
        assert distance <= SETTINGS.service_region_radius_m, n.id


def test_a_region_that_excludes_a_neighborhood_refuses_to_start(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_REGION_RADIUS_M", "5000")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "Sébikotane" in str(exc_info.value)


def test_a_long_window_limit_below_the_short_one_refuses_to_start(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTISAN_LOCATION_CHANGES_SHORT_MAX", "5")
    monkeypatch.setenv("ARTISAN_LOCATION_CHANGES_LONG_MAX", "4")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "ARTISAN_LOCATION_CHANGES_LONG_MAX" in str(exc_info.value)


# --- Grille et arrondi ------------------------------------------------------------


def _grid_snap(lat: float, lng: float) -> tuple[float, float]:
    return snap_to_grid(
        lat,
        lng,
        grid_m=SETTINGS.artisan_gps_grid_m,
        reference_lat=SETTINGS.service_region_center_lat,
    )


def test_two_positions_of_the_same_cell_give_exactly_the_same_point() -> None:
    node = _grid_snap(14.70, -17.45)
    quarter = SETTINGS.artisan_gps_grid_m / 4 / METERS_PER_DEGREE
    around = [
        (node[0] + quarter, node[1] - quarter),
        (node[0] - quarter, node[1] + quarter),
        (node[0] + quarter / 2, node[1] + quarter / 3),
    ]

    assert {_grid_snap(lat, lng) for lat, lng in around} == {node}


def test_the_stored_point_is_at_most_half_a_cell_diagonal_away() -> None:
    limit = SETTINGS.artisan_gps_grid_m * math.sqrt(2) / 2
    for i in range(40):
        lat, lng = 14.60 + i * 0.0071, -17.52 + i * 0.0093
        snapped = _grid_snap(lat, lng)
        # Marge de 1 % : le pas en longitude est calculé à la latitude de
        # référence, la maille réelle varie un peu avec la latitude.
        assert haversine_m(lat, lng, *snapped) <= limit * 1.01


@pytest.mark.parametrize(
    ("distance", "expected_steps"),
    [(0, 1), (1, 1), (499.9, 1), (500, 1), (500.1, 2), (1_234, 3)],
)
def test_public_distances_round_up_to_the_step(distance: float, expected_steps: int) -> None:
    step = SETTINGS.public_distance_rounding_m
    scaled = distance * step / 500  # mêmes proportions quel que soit le pas réglé

    assert round_public_distance(scaled, step_m=step) == expected_steps * step


# --- Exposition publique et migration ----------------------------------------------


async def test_the_public_list_is_the_backend_one_with_aliases_and_region() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/v1/meta/neighborhoods")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [n.id for n in NEIGHBORHOODS]
    first = body["items"][0]
    assert set(first) == {
        "id",
        "label",
        "commune",
        "department",
        "department_label",
        "lat",
        "lng",
    }
    assert body["aliases"] == LEGACY_ALIASES
    assert body["default_id"] == DEFAULT_NEIGHBORHOOD_ID
    assert resolve_neighborhood(DEFAULT_NEIGHBORHOOD_ID) is not None
    assert body["service_region"] == {
        "center_lat": SETTINGS.service_region_center_lat,
        "center_lng": SETTINGS.service_region_center_lng,
        "radius_m": SETTINGS.service_region_radius_m,
    }


def test_the_migration_creates_exactly_the_model_consistency_check() -> None:
    spec = importlib.util.spec_from_file_location("zone_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.LOCATION_FIELDS_CONSISTENT_SQL == LOCATION_FIELDS_CONSISTENT_SQL
