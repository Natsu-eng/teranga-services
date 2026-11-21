"""Vie privée de la position des artisans : une triangulation depuis
plusieurs points ne retrouve QUE le point enregistré (nœud de grille ou
centre de quartier), jamais la position réelle.

Méthode : deux artisans se placent par GPS à deux positions RÉELLES
différentes d'une même maille. Si toutes les réponses publiques (recherche
par proximité, couverture) sont identiques pour eux depuis trois points
d'observation, aucune combinaison de ces réponses ne peut distinguer leurs
positions réelles : au mieux, elle retrouve le point arrondi qu'ils
partagent. Même preuve pour deux artisans placés au centre d'un quartier.
"""

from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_X, ST_Y
from httpx import ASGITransport, AsyncClient
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.geo_privacy import METERS_PER_DEGREE, snap_to_grid
from app.core.neighborhoods import resolve_neighborhood
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role, VerificationDocType, VerificationStatus
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_trade,
    make_user,
    make_verification,
)

SETTINGS = get_settings()
# Trois points d'observation autour du Plateau / de la Médina.
OBSERVERS = [(14.6900, -17.4400), (14.6700, -17.4700), (14.7100, -17.4600)]


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


async def _visible_artisan(db_session: AsyncSession, trade: Trade) -> tuple[User, ArtisanProfile]:
    """Artisan vérifié, NON placé, exerçant `trade` sur un rayon large."""
    user = await make_user(db_session, role=Role.ARTISAN)
    profile = await make_artisan_profile(db_session, user=user, placed=False)
    await make_artisan_trade(
        db_session,
        artisan=profile,
        trade=trade,
        service_radius_m=SETTINGS.artisan_service_radius_max_m,
    )
    for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
        await make_verification(
            db_session, artisan=profile, doc_type=doc_type, status=VerificationStatus.APPROVED
        )
    return user, profile


async def _place(http: AsyncClient, user: User, location: dict[str, Any]) -> None:
    response = await http.patch(
        "/api/v1/artisans/me", json={"location": location}, headers=_auth(user)
    )
    assert response.status_code == 200, response.text


async def _stored_point(db_session: AsyncSession, profile: ArtisanProfile) -> tuple[float, float]:
    geometry = cast(ArtisanProfile.base_location, Geometry)
    row = (
        await db_session.execute(
            select(ST_Y(geometry), ST_X(geometry)).where(ArtisanProfile.id == profile.id)
        )
    ).one()
    return float(row[0]), float(row[1])


async def _observations(
    http: AsyncClient, trade: Trade, profiles: list[ArtisanProfile]
) -> list[list[Any]]:
    """Pour chaque artisan : tout ce que le public apprend de lui depuis les
    trois points (distance publique, couverture)."""
    seen: list[list[Any]] = [[] for _ in profiles]
    for lat, lng in OBSERVERS:
        search = await http.get(
            "/api/v1/artisans",
            params={
                "near": f"{lat},{lng}",
                "trade": trade.code,
                "radius_m": SETTINGS.artisan_search_max_radius_m,
            },
        )
        assert search.status_code == 200, search.text
        distances = {item["id"]: item["distance_m"] for item in search.json()["items"]}
        for index, profile in enumerate(profiles):
            coverage = await http.get(
                f"/api/v1/artisans/{profile.id}/coverage",
                params={"trade": trade.code, "lat": lat, "lng": lng},
            )
            assert coverage.status_code == 200, coverage.text
            distance = distances[str(profile.id)]
            assert distance % SETTINGS.public_distance_rounding_m == 0
            seen[index].append((distance, coverage.json()))
    return seen


async def test_gps_triangulation_only_finds_the_rounded_point(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    (user_a, a), (user_b, b) = (
        await _visible_artisan(db_session, trade),
        await _visible_artisan(db_session, trade),
    )
    node = snap_to_grid(
        14.6900,
        -17.4500,
        grid_m=SETTINGS.artisan_gps_grid_m,
        reference_lat=SETTINGS.service_region_center_lat,
    )
    # Deux positions réelles distinctes de la même maille (~1/4 de maille
    # de part et d'autre du nœud).
    offset = SETTINGS.artisan_gps_grid_m / 4 / METERS_PER_DEGREE
    real_a = (node[0] + offset, node[1] - offset)
    real_b = (node[0] - offset, node[1] + offset / 2)

    async with _client() as http:
        await _place(http, user_a, {"source": "gps", "lat": real_a[0], "lng": real_a[1]})
        await _place(http, user_b, {"source": "gps", "lat": real_b[0], "lng": real_b[1]})
        seen_a, seen_b = await _observations(http, trade, [a, b])

    assert await _stored_point(db_session, a) == node
    assert await _stored_point(db_session, b) == node
    # Réponses publiques identiques depuis chaque point d'observation : les
    # positions réelles sont indiscernables, seul le nœud est trouvable.
    assert seen_a == seen_b


async def test_neighborhood_triangulation_only_finds_the_center(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    (user_a, a), (user_b, b) = (
        await _visible_artisan(db_session, trade),
        await _visible_artisan(db_session, trade),
    )
    medina = resolve_neighborhood("medina")
    assert medina is not None

    async with _client() as http:
        for user in (user_a, user_b):
            await _place(http, user, {"source": "neighborhood", "neighborhood_id": "medina"})
        seen_a, seen_b = await _observations(http, trade, [a, b])

    assert await _stored_point(db_session, a) == (medina.lat, medina.lng)
    assert await _stored_point(db_session, b) == (medina.lat, medina.lng)
    assert seen_a == seen_b
