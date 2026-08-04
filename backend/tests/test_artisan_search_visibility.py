"""Éligibilité à la recherche publique (BUILD_PLAN.md, onboarding artisan) :
un artisan dont `verified_status != VERIFIED` est invisible sur
`GET /api/v1/artisans` -- décision actée, voir le commentaire détaillé dans
`app.services.artisans.list_artisans`. Le détail (`GET /artisans/{id}`)
reste accessible quel que soit le statut : c'est ce qui permet à l'artisan
lui-même de voir son propre profil pendant l'onboarding (`/pro`).
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import ArtisanVerifiedStatus, Role
from tests.factories import make_artisan_profile, make_artisan_trade, make_trade, make_user

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


@pytest.mark.parametrize(
    "status",
    [ArtisanVerifiedStatus.NONE, ArtisanVerifiedStatus.PENDING, ArtisanVerifiedStatus.REJECTED],
)
async def test_unverified_artisan_is_absent_from_public_search(
    db_session: AsyncSession, status: ArtisanVerifiedStatus
) -> None:
    trade = await make_trade(db_session, code="plomberie")
    artisan = await make_artisan_profile(
        db_session, lat=REFERENCE_LAT, lng=REFERENCE_LNG, is_available=True
    )
    artisan.verified_status = status
    await db_session.flush()
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(artisan.id) not in ids


async def test_verified_artisan_is_present_in_public_search(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session, code="electricite")
    artisan = await make_artisan_profile(
        db_session, lat=REFERENCE_LAT, lng=REFERENCE_LNG, is_available=True
    )
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(artisan.id) in ids


async def test_unverified_artisan_can_still_view_own_detail_profile(
    db_session: AsyncSession,
) -> None:
    """Contrairement à la recherche, `GET /artisans/{id}` reste accessible
    quel que soit `verified_status` -- indispensable pour que l'artisan
    voie son propre profil pendant l'onboarding (écran `/pro`)."""
    owner_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner_user)
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await db_session.flush()
    token = encode_access_token(owner_user)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["verified_status"] == "none"
