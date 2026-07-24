"""Requête de proximité PostGIS (ST_DWithin) triée par distance."""

from geoalchemy2.functions import ST_Distance, ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanProfile
from tests.factories import make_artisan_profile, point

# Le Plateau, Dakar -- point de référence pour la recherche de proximité.
REFERENCE_LAT = 14.6937
REFERENCE_LNG = -17.4441


async def test_st_dwithin_returns_nearby_artisans_sorted_by_distance(
    db_session: AsyncSession,
) -> None:
    # ~0.1 km du point de référence (même quartier, Le Plateau).
    near = await make_artisan_profile(db_session, lat=14.6945, lng=-17.4448)
    # ~5.9 km du point de référence (Ouakam).
    mid = await make_artisan_profile(db_session, lat=14.7256, lng=-17.4914)
    # ~1500 km du point de référence (hors rayon de recherche).
    far = await make_artisan_profile(db_session, lat=6.5244, lng=3.3792)  # Lagos

    reference = point(REFERENCE_LAT, REFERENCE_LNG)
    radius_m = 10_000  # 10 km

    result = await db_session.execute(
        select(ArtisanProfile)
        .where(
            ArtisanProfile.id.in_([near.id, mid.id, far.id]),
            ST_DWithin(ArtisanProfile.base_location, reference, radius_m),
        )
        .order_by(ST_Distance(ArtisanProfile.base_location, reference))
    )
    ordered_ids = [row.id for row in result.scalars().all()]

    assert ordered_ids == [near.id, mid.id]  # far exclu, near avant mid
