"""Test d'intégration de GET /api/v1/artisans (BUILD_PLAN.md §6 Lot 9)."""

from collections.abc import AsyncGenerator, Generator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from scripts.seed import ARTISANS, _seed_artisans, _seed_trades, seed
from tests.factories import make_artisan_profile, make_artisan_trade, make_trade

REFERENCE_LAT = 14.6937
REFERENCE_LNG = -17.4441


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_list_returns_paginated_envelope_with_idrissa_at_zero_distance(
    db_session: AsyncSession,
) -> None:
    # Le seed COMPLET (métiers, artisans, avis, notes recalculées) tourne dans
    # la transaction du test, annulée à la fin : la note et les avis vérifiés
    # ci-dessous sont garantis par construction, jamais hérités de l'état de
    # la base de dev (qui peut être vide, ou contenir d'autres comptes réels).
    await seed(db_session)
    trades = await _seed_trades(db_session)
    artisan_profiles = await _seed_artisans(db_session, trades)
    idrissa = next(a for a in ARTISANS if a["full_name"] == "Idrissa Diop")
    idrissa_id = str(artisan_profiles[idrissa["phone"]].id)

    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )

    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "pagination" in body
    # Le total dépend aussi des comptes réels éventuellement présents dans la
    # base de dev : seule la forme de l'enveloppe et la présence d'Idrissa
    # sont vérifiées, jamais un total exact.
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == get_settings().pagination_page_size_default
    assert body["pagination"]["total"] >= 1
    item = next(i for i in body["items"] if i["id"] == idrissa_id)
    assert item["distance_m"] == 0
    assert item["full_name"] == "Idrissa Diop"
    assert item["trades"][0]["trade"]["code"] == "plomberie"
    assert item["verified_status"] == "verified"
    assert item["rating_avg"] == 5.0
    assert item["review_count"] == 2


async def test_list_combines_trade_min_rating_available_and_q_filters(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session, code="plomberie")
    other_trade = await make_trade(db_session, code="electricite")

    matching = await make_artisan_profile(db_session, bio="Spécialiste fuite d'eau.")
    await make_artisan_trade(db_session, artisan=matching, trade=trade)
    matching.rating_avg = Decimal("4.80")
    await db_session.flush()

    wrong_trade = await make_artisan_profile(db_session, bio="Spécialiste fuite d'eau.")
    await make_artisan_trade(db_session, artisan=wrong_trade, trade=other_trade)
    wrong_trade.rating_avg = Decimal("4.80")

    low_rating = await make_artisan_profile(db_session, bio="Spécialiste fuite d'eau.")
    await make_artisan_trade(db_session, artisan=low_rating, trade=trade)
    low_rating.rating_avg = Decimal("2.00")

    unavailable = await make_artisan_profile(
        db_session, bio="Spécialiste fuite d'eau.", is_available=False
    )
    await make_artisan_trade(db_session, artisan=unavailable, trade=trade)
    unavailable.rating_avg = Decimal("4.80")
    await db_session.flush()

    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans",
            params={
                "trade": trade.code,
                "min_rating": 4.0,
                "available": "true",
                "q": "fuite",
                "page_size": 50,
            },
        )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(matching.id) in ids
    assert str(wrong_trade.id) not in ids
    assert str(low_rating.id) not in ids
    assert str(unavailable.id) not in ids


async def test_invalid_near_returns_normalized_422() -> None:
    async with await _client() as client:
        response = await client.get("/api/v1/artisans", params={"near": "pas-une-position"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POSITION_INVALIDE"


async def test_sort_distance_without_near_returns_normalized_422() -> None:
    async with await _client() as client:
        response = await client.get("/api/v1/artisans", params={"sort": "distance"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TRI_DISTANCE_SANS_POSITION"


async def test_page_beyond_hard_cap_returns_normalized_422() -> None:
    max_page = get_settings().pagination_max_page
    async with await _client() as client:
        response = await client.get("/api/v1/artisans", params={"page": max_page + 1})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PAGE_HORS_BORNES"


async def test_page_beyond_actual_results_returns_200_with_empty_items() -> None:
    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans", params={"trade": "un-metier-qui-nexiste-pas-xyz", "page": 2}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["pagination"]["total"] == 0
