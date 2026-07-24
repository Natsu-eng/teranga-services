"""Repository artisans : recherche géo, filtres, count (BUILD_PLAN.md §5, §6 Lot 9)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.repositories.artisans import (
    ArtisanSearchFilters,
    count_artisans,
    get_artisan_by_id,
    search_artisans,
)
from scripts.seed import ARTISANS, _seed_artisans, _seed_trades
from tests.factories import (
    bounding_box_polygon,
    make_artisan_profile,
    make_artisan_trade,
    make_trade,
    make_user,
    make_verification,
)

# Le Plateau, Dakar -- mêmes coordonnées que tests/test_geo.py.
REFERENCE_LAT = 14.6937
REFERENCE_LNG = -17.4441


async def _search_ids(session: AsyncSession, filters: ArtisanSearchFilters) -> set[uuid.UUID]:
    results = await search_artisans(session, filters, limit=50, offset=0)
    return {profile.id for profile, _ in results}


async def test_search_against_seeded_artisans_combines_client_radius_and_own_service_radius(
    db_session: AsyncSession,
) -> None:
    """Contre les 3 artisans réellement semés (Plateau/Ouakam/Almadies).

    Chacun a un `service_radius_m` de 5 km par défaut (donnée de seed, Lot 7).
    Depuis la référence (position d'Idrissa, Le Plateau), Maty (~6,2km) et
    Ousmane (~9,3km) sont tous les deux hors de portée de LEUR PROPRE zone
    d'intervention (5km) -- même avec un rayon client large, ils ne
    devraient pas apparaître. Seul Idrissa (0m, dans sa propre zone) est
    trouvé. C'est la combinaison attendue : rayon client ET zone artisan.
    """
    trades = await _seed_trades(db_session)
    artisan_profiles = await _seed_artisans(db_session, trades)
    by_name = {a["full_name"]: artisan_profiles[a["phone"]] for a in ARTISANS}
    idrissa = by_name["Idrissa Diop"]
    maty = by_name["Maty Ndiaye"]
    ousmane = by_name["Ousmane Fall"]

    filters = ArtisanSearchFilters(
        near=(REFERENCE_LAT, REFERENCE_LNG), radius_m=10_000, sort="distance"
    )
    results = await search_artisans(db_session, filters, limit=10, offset=0)
    relevant = [(p, d) for p, d in results if p.id in {idrissa.id, maty.id, ousmane.id}]

    assert [p.id for p, _ in relevant] == [idrissa.id]
    idrissa_distance = relevant[0][1]
    assert idrissa_distance is not None
    assert idrissa_distance <= 5


async def test_sort_by_distance_orders_reachable_artisans_correctly(
    db_session: AsyncSession,
) -> None:
    """Isole l'ordre de tri par distance de la contrainte de zone
    d'intervention : deux artisans synthétiques, tous deux avec un
    `service_radius_m` assez large pour couvrir la référence, à des
    distances différentes -- le plus proche doit sortir en premier.
    """
    trade = await make_trade(db_session)
    near = await make_artisan_profile(db_session, lat=14.6945, lng=-17.4448)  # ~0,1km
    await make_artisan_trade(db_session, artisan=near, trade=trade, service_radius_m=20_000)
    mid = await make_artisan_profile(db_session, lat=14.7256, lng=-17.4914)  # ~6,2km (Ouakam)
    await make_artisan_trade(db_session, artisan=mid, trade=trade, service_radius_m=20_000)

    filters = ArtisanSearchFilters(
        near=(REFERENCE_LAT, REFERENCE_LNG), radius_m=10_000, sort="distance"
    )
    results = await search_artisans(db_session, filters, limit=10, offset=0)
    relevant = [(p, d) for p, d in results if p.id in {near.id, mid.id}]

    assert [p.id for p, _ in relevant] == [near.id, mid.id]


async def test_search_without_near_does_not_fail_and_sorts_by_rating_by_default(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    low = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=low, trade=trade)
    low.rating_avg = Decimal("3.00")

    high = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=high, trade=trade)
    high.rating_avg = Decimal("4.80")
    await db_session.flush()

    filters = ArtisanSearchFilters(trade_code=trade.code)
    results = await search_artisans(db_session, filters, limit=10, offset=0)

    ids_in_order = [p.id for p, _ in results]
    assert ids_in_order.index(high.id) < ids_in_order.index(low.id)
    assert all(distance is None for _, distance in results)


async def test_artisan_beyond_own_service_radius_excluded_even_within_client_radius(
    db_session: AsyncSession,
) -> None:
    trades = await _seed_trades(db_session)
    artisan_profiles = await _seed_artisans(db_session, trades)
    ousmane = next(
        artisan_profiles[a["phone"]] for a in ARTISANS if a["full_name"] == "Ousmane Fall"
    )

    # Ousmane (Almadies, ~9,3km de la référence) : dans le rayon client (10km)
    # mais hors de son propre service_radius_m par défaut (5km, sans polygone).
    filters = ArtisanSearchFilters(near=(REFERENCE_LAT, REFERENCE_LNG), radius_m=10_000)

    assert ousmane.id not in await _search_ids(db_session, filters)


async def test_service_area_polygon_overrides_service_radius_fallback(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    # ~9,3km de la référence -- hors service_radius_m par défaut (5km).
    artisan = await make_artisan_profile(db_session, lat=14.7444, lng=-17.5133)
    covering_polygon = bounding_box_polygon(
        min_lat=14.60, max_lat=14.80, min_lng=-17.60, max_lng=-17.35
    )
    await make_artisan_trade(
        db_session,
        artisan=artisan,
        trade=trade,
        service_radius_m=5_000,
        service_area=covering_polygon,
    )

    filters = ArtisanSearchFilters(near=(REFERENCE_LAT, REFERENCE_LNG), radius_m=10_000)

    assert artisan.id in await _search_ids(db_session, filters)


async def test_min_rating_excludes_artisans_with_null_rating(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    rated = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=rated, trade=trade)
    rated.rating_avg = Decimal("4.50")

    unrated = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=unrated, trade=trade)
    await db_session.flush()

    filters = ArtisanSearchFilters(min_rating=Decimal("4.00"))
    ids = await _search_ids(db_session, filters)

    assert rated.id in ids
    assert unrated.id not in ids


async def test_available_filter(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    available = await make_artisan_profile(db_session, is_available=True)
    await make_artisan_trade(db_session, artisan=available, trade=trade)
    unavailable = await make_artisan_profile(db_session, is_available=False)
    await make_artisan_trade(db_session, artisan=unavailable, trade=trade)

    filters = ArtisanSearchFilters(available=True)
    ids = await _search_ids(db_session, filters)

    assert available.id in ids
    assert unavailable.id not in ids


async def test_q_matches_full_name_or_bio_case_insensitively(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    named_user = await make_user(db_session, role=Role.ARTISAN, full_name="Awa Ndiaye")
    matched_by_name = await make_artisan_profile(
        db_session, user=named_user, bio="Rien de spécial."
    )
    await make_artisan_trade(db_session, artisan=matched_by_name, trade=trade)

    matched_by_bio = await make_artisan_profile(
        db_session, bio="Spécialiste climatisation Inverter."
    )
    await make_artisan_trade(db_session, artisan=matched_by_bio, trade=trade)

    unrelated = await make_artisan_profile(db_session, bio="Menuiserie sur mesure.")
    await make_artisan_trade(db_session, artisan=unrelated, trade=trade)

    by_name_ids = await _search_ids(db_session, ArtisanSearchFilters(q="awa"))
    assert matched_by_name.id in by_name_ids
    assert matched_by_bio.id not in by_name_ids
    assert unrelated.id not in by_name_ids

    by_bio_ids = await _search_ids(db_session, ArtisanSearchFilters(q="INVERTER"))
    assert matched_by_bio.id in by_bio_ids
    assert matched_by_name.id not in by_bio_ids


async def test_trade_filter_excludes_artisans_of_other_trades(db_session: AsyncSession) -> None:
    trade_a = await make_trade(db_session, code="plomberie")
    trade_b = await make_trade(db_session, code="electricite")
    matching = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=matching, trade=trade_a)
    other = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=other, trade=trade_b)

    filters = ArtisanSearchFilters(trade_code=trade_a.code)
    ids = await _search_ids(db_session, filters)

    assert matching.id in ids
    assert other.id not in ids


async def test_artisan_without_any_trade_never_appears(db_session: AsyncSession) -> None:
    artisan = await make_artisan_profile(db_session)  # aucun artisan_trade créé

    ids = await _search_ids(db_session, ArtisanSearchFilters())

    assert artisan.id not in ids


async def test_soft_deleted_artisan_excluded_everywhere(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    artisan.deleted_at = datetime.now(UTC)
    await db_session.flush()

    ids = await _search_ids(db_session, ArtisanSearchFilters())
    assert artisan.id not in ids
    assert await get_artisan_by_id(db_session, artisan.id) is None


async def test_artisan_with_soft_deleted_user_excluded_everywhere(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=user)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    user.deleted_at = datetime.now(UTC)
    await db_session.flush()

    ids = await _search_ids(db_session, ArtisanSearchFilters())
    assert artisan.id not in ids
    assert await get_artisan_by_id(db_session, artisan.id) is None


async def test_count_artisans_matches_unpaginated_search_length(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    for _ in range(3):
        artisan = await make_artisan_profile(db_session)
        await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    filters = ArtisanSearchFilters(trade_code=trade.code)
    count = await count_artisans(db_session, filters)
    results = await search_artisans(db_session, filters, limit=50, offset=0)

    assert count == len(results) == 3


async def test_search_eager_loads_user_trades_and_verifications(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    await make_verification(db_session, artisan=artisan)

    filters = ArtisanSearchFilters(trade_code=trade.code)
    results = await search_artisans(db_session, filters, limit=50, offset=0)
    profile = next(p for p, _ in results if p.id == artisan.id)

    assert profile.user.full_name  # pas de lazy-load raté (MissingGreenlet)
    assert profile.artisan_trades[0].trade.code == trade.code
    assert len(profile.verifications) == 1


async def test_get_artisan_by_id_returns_full_profile(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    found = await get_artisan_by_id(db_session, artisan.id)

    assert found is not None
    assert found.id == artisan.id


async def test_get_artisan_by_id_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    assert await get_artisan_by_id(db_session, uuid.uuid4()) is None
