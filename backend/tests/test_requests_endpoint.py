"""Test d'intégration de `/api/v1/requests` (BUILD_PLAN.md §3.2, §6 Lot 12)."""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
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


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


def _create_payload(trade_code: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_code": trade_code,
        "description": "Le robinet fuit sous l'évier.",
        "location": {"lat": 14.6937, "lng": -17.4441},
        "urgency": "urgent",
    }
    payload.update(overrides)
    return payload


async def test_create_request_nominal(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    trade = await make_trade(db_session, code="plomberie")

    async with await _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json=_create_payload(
                trade.code, ai_estimate_min_fcfa=8_000, ai_estimate_max_fcfa=15_000
            ),
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["trade"]["code"] == trade.code
    assert body["status"] == "ouverte"
    assert body["urgency"] == "urgent"
    assert body["client_id"] == str(client_user.id)
    assert body["location"]["lat"] == pytest.approx(14.6937, abs=1e-4)
    assert body["location"]["lng"] == pytest.approx(-17.4441, abs=1e-4)
    assert body["ai_estimate_min_fcfa"] == 8_000
    assert body["ai_estimate_max_fcfa"] == 15_000


async def test_create_request_unknown_trade_returns_normalized_422(
    db_session: AsyncSession,
) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json=_create_payload("un-metier-qui-nexiste-pas-xyz"),
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "METIER_INCONNU"


async def test_create_request_requires_authentication(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)

    async with await _client() as http:
        response = await http.post("/api/v1/requests", json=_create_payload(trade.code))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NON_AUTHENTIFIE"


async def test_create_request_rejects_artisan_role(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    trade = await make_trade(db_session)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json=_create_payload(trade.code),
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_create_request_rejects_incoherent_ai_estimate(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    trade = await make_trade(db_session)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json=_create_payload(
                trade.code, ai_estimate_min_fcfa=20_000, ai_estimate_max_fcfa=10_000
            ),
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ESTIMATION_IA_INVALIDE"


async def test_create_request_rejects_partial_ai_estimate(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    trade = await make_trade(db_session)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json=_create_payload(trade.code, ai_estimate_min_fcfa=10_000),
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ESTIMATION_IA_INVALIDE"


async def test_list_my_requests_is_isolated_per_client_and_sorted_by_date_desc(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    me = await make_user(db_session, role=Role.CLIENT)
    someone_else = await make_user(db_session, role=Role.CLIENT)

    older = await make_service_request(db_session, client=me, trade=trade)
    newer = await make_service_request(db_session, client=me, trade=trade)
    await make_service_request(db_session, client=someone_else, trade=trade)

    async with await _client() as http:
        response = await http.get("/api/v1/requests/me", headers=_auth_headers(me))

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert ids == [str(newer.id), str(older.id)]
    assert body["pagination"]["total"] == 2


async def test_get_request_by_owner_succeeds(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await make_service_request(db_session, client=client_user, trade=trade)

    async with await _client() as http:
        response = await http.get(
            f"/api/v1/requests/{request.id}", headers=_auth_headers(client_user)
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(request.id)


async def test_get_request_by_unrelated_client_is_forbidden(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.CLIENT)
    stranger = await make_user(db_session, role=Role.CLIENT)
    request = await make_service_request(db_session, client=owner, trade=trade)

    async with await _client() as http:
        response = await http.get(f"/api/v1/requests/{request.id}", headers=_auth_headers(stranger))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SERVICE_REQUEST_ACCES_INTERDIT"


async def test_get_request_by_concerned_artisan_succeeds(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.CLIENT)
    request = await make_service_request(db_session, client=owner, trade=trade)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    await make_intervention(
        db_session, service_request=request, client=owner, artisan=artisan, commission_rate=rate
    )

    async with await _client() as http:
        response = await http.get(
            f"/api/v1/requests/{request.id}", headers=_auth_headers(artisan_user)
        )

    assert response.status_code == 200


async def test_get_request_by_unrelated_artisan_is_forbidden(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.CLIENT)
    request = await make_service_request(db_session, client=owner, trade=trade)
    unrelated_artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=unrelated_artisan_user)

    async with await _client() as http:
        response = await http.get(
            f"/api/v1/requests/{request.id}", headers=_auth_headers(unrelated_artisan_user)
        )

    assert response.status_code == 403


async def test_get_unknown_request_returns_404(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        response = await http.get(
            "/api/v1/requests/00000000-0000-0000-0000-000000000000",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SERVICE_REQUEST_NOT_FOUND"
