"""Test d'intégration de GET /api/v1/artisans/{id} (BUILD_PLAN.md §6 Lot 9)."""

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.enums import Role, VerificationDocType, VerificationStatus
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_trade,
    make_user,
    make_verification,
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


async def test_get_artisan_returns_full_profile_with_derived_verified_status(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session, bio="Un artisan de test.")
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, hourly_rate_fcfa=12_000)
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.APPROVED,
    )
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.SELFIE,
        status=VerificationStatus.APPROVED,
    )

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(artisan.id)
    assert body["verified_status"] == "verified"
    assert body["trades"][0]["hourly_rate_fcfa"] == 12_000
    assert body["trades"][0]["trade"]["code"] == trade.code
    assert "created_at" in body
    assert "distance_m" not in body or body["distance_m"] is None


async def test_get_artisan_verified_status_reflects_verification_changes(
    db_session: AsyncSession,
) -> None:
    """`verified_status` est calculé à la volée depuis les lignes
    `verification`, jamais lu depuis la colonne stockée -- une évolution des
    documents change la réponse sans qu'on touche `artisan_profile.verified_status`.
    """
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.APPROVED,
    )
    # SELFIE jamais soumis : la colonne stockée est VERIFIED (valeur par
    # défaut de la factory), mais la valeur dérivée doit être PENDING.

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.json()["verified_status"] == "pending"


async def test_get_artisan_returns_normalized_404_for_unknown_id() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTISAN_NOT_FOUND"


async def test_get_artisan_returns_404_for_soft_deleted_artisan(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    artisan.deleted_at = datetime.now(UTC)
    await db_session.flush()

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 404


async def test_get_artisan_returns_404_for_soft_deleted_user(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=user)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    user.deleted_at = datetime.now(UTC)
    await db_session.flush()

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 404
