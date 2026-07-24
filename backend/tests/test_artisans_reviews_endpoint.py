"""Test d'intégration de GET /api/v1/artisans/{id}/reviews (BUILD_PLAN.md §6 Lot 9)."""

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.commission import CommissionRate
from app.models.enums import ReviewStatus, Role
from app.models.review import Review
from app.models.trade import Trade
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_review,
    make_service_request,
    make_trade,
    make_user,
)


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


async def _make_review(
    db_session: AsyncSession,
    artisan: ArtisanProfile,
    trade: Trade,
    commission_rate: CommissionRate,
    *,
    rating: int,
    status: ReviewStatus,
    author_name: str,
) -> Review:
    author = await make_user(db_session, role=Role.CLIENT, full_name=author_name)
    service_request = await make_service_request(db_session, client=author, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=author,
        artisan=artisan,
        commission_rate=commission_rate,
    )
    return await make_review(
        db_session,
        intervention=intervention,
        author=author,
        artisan=artisan,
        rating=rating,
        status=status,
    )


async def test_reviews_list_excludes_hidden_reviews(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)

    published = await _make_review(
        db_session,
        artisan,
        trade,
        commission_rate,
        rating=5,
        status=ReviewStatus.PUBLIE,
        author_name="Fatou K.",
    )
    await _make_review(
        db_session,
        artisan,
        trade,
        commission_rate,
        rating=1,
        status=ReviewStatus.MASQUE,
        author_name="Avis masqué",
    )

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}/reviews")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(published.id)
    assert body["items"][0]["author_name"] == "Fatou K."


async def test_reviews_list_is_paginated(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    for i in range(3):
        await _make_review(
            db_session,
            artisan,
            trade,
            commission_rate,
            rating=5,
            status=ReviewStatus.PUBLIE,
            author_name=f"Client {i}",
        )

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}/reviews", params={"page_size": 2, "page": 1}
        )

    body = response.json()
    assert len(body["items"]) == 2
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["total_pages"] == 2


async def test_reviews_list_returns_normalized_404_for_unknown_artisan() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{uuid.uuid4()}/reviews")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTISAN_NOT_FOUND"
