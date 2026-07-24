"""Aucune réponse sérialisée de ce lot ne doit exposer téléphone, email ou
coordonnées brutes (BUILD_PLAN.md §2.2, §6 Lot 9) -- c'est la protection
principale contre la désintermédiation. Test transversal, exercé sur
chacun des endpoints de lecture des artisans.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import InterventionStatus, PaymentStatus, Role
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_intervention,
    make_payment,
    make_review,
    make_service_request,
    make_trade,
    make_user,
    make_verification,
)

# Fragments de clé interdits, insensibles à la casse -- couvre phone/email et
# toute variante de coordonnées brutes (lat, lng, latitude, longitude,
# location/base_location).
_FORBIDDEN_KEY_FRAGMENTS = ("phone", "email", "lat", "lng", "latitude", "longitude", "location")


def _assert_no_forbidden_keys(value: object, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            lowered = str(key).lower()
            assert not any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS), (
                f"clé interdite {key!r} trouvée à {path}.{key}"
            )
            _assert_no_forbidden_keys(sub, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_keys(item, path=f"{path}[{index}]")


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


async def test_no_pii_in_list_response(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    await make_verification(db_session, artisan=artisan)

    async with await _client() as client:
        response = await client.get("/api/v1/artisans", params={"trade": trade.code})

    assert response.status_code == 200
    _assert_no_forbidden_keys(response.json())


async def test_no_pii_in_detail_response(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 200
    _assert_no_forbidden_keys(response.json())


async def test_no_pii_in_reviews_response(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    author = await make_user(db_session, role=Role.CLIENT, full_name="Fatou K.")
    service_request = await make_service_request(db_session, client=author, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=author,
        artisan=artisan,
        commission_rate=commission_rate,
        status=InterventionStatus.TERMINEE,
    )
    await make_review(db_session, intervention=intervention, author=author, artisan=artisan)

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}/reviews")

    assert response.status_code == 200
    _assert_no_forbidden_keys(response.json())


async def test_no_pii_in_public_stats_response(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}/stats")

    assert response.status_code == 200
    _assert_no_forbidden_keys(response.json())


async def test_no_pii_in_private_stats_response(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=owner)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    client_user = await make_user(db_session, role=Role.CLIENT)
    service_request = await make_service_request(db_session, client=client_user, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client_user,
        artisan=artisan,
        commission_rate=commission_rate,
        status=InterventionStatus.TERMINEE,
    )
    await make_payment(
        db_session, intervention=intervention, amount_fcfa=10_000, status=PaymentStatus.REUSSI
    )
    token = encode_access_token(owner)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/artisans/{artisan.id}/stats", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["revenue_fcfa"] == 10_000  # confirme qu'on inspecte bien la vue "riche"
    _assert_no_forbidden_keys(body)
