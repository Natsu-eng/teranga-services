"""Requête de proximité PostGIS (ST_DWithin) triée par distance."""

from geoalchemy2.functions import ST_Distance, ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanProfile
from scripts.seed import ARTISANS, _seed_artisans, _seed_trades
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


async def test_st_dwithin_orders_seeded_artisans_by_distance_from_a_reference_point(
    db_session: AsyncSession,
) -> None:
    """Contre les 3 artisans réellement semés par scripts/seed.py (Plateau,
    Ouakam, Almadies) -- pas des artisans synthétiques. `_seed_trades` /
    `_seed_artisans` sont get-or-create : si `scripts/seed.py` a déjà tourné
    sur cette base, on retrouve les mêmes lignes ; sinon on les crée dans
    cette transaction, qui de toute façon n'est jamais commitée.

    Distances réelles mesurées via ST_Distance depuis Le Plateau : Idrissa
    Diop 0 m, Maty Ndiaye (Ouakam) ~6 197 m, Ousmane Fall (Almadies)
    ~9 328 m.
    """
    trades = await _seed_trades(db_session)
    artisan_profiles = await _seed_artisans(db_session, trades)
    by_name = {a["full_name"]: artisan_profiles[a["phone"]] for a in ARTISANS}

    idrissa = by_name["Idrissa Diop"]  # Le Plateau -- 0 m du point de référence
    maty = by_name["Maty Ndiaye"]  # Ouakam -- ~6 197 m
    ousmane = by_name["Ousmane Fall"]  # Almadies -- ~9 328 m (hors rayon)

    reference = point(REFERENCE_LAT, REFERENCE_LNG)
    radius_m = 7_000  # sépare nettement Maty (~6,2 km) d'Ousmane (~9,3 km)

    result = await db_session.execute(
        select(ArtisanProfile)
        .where(
            ArtisanProfile.id.in_([idrissa.id, maty.id, ousmane.id]),
            ST_DWithin(ArtisanProfile.base_location, reference, radius_m),
        )
        .order_by(ST_Distance(ArtisanProfile.base_location, reference))
    )
    ordered_ids = [row.id for row in result.scalars().all()]

    assert ordered_ids == [idrissa.id, maty.id]  # Ousmane (Almadies) exclu du rayon
