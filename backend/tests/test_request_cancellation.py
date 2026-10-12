"""Annulation d'une demande par son client : `POST /requests/{id}/cancel`.

Annulation, jamais suppression : la demande reste en historique avec le
statut `annulee`, et ne peut plus être adressée à un artisan.
"""

from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role, ServiceRequestStatus, VerificationDocType, VerificationStatus
from app.models.request import ServiceRequest
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_service_request,
    make_trade,
    make_user,
    make_verification,
)


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Iterator[None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.pop(get_session, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _request(
    db_session: AsyncSession,
    *,
    client: User,
    trade: Trade,
    status: ServiceRequestStatus = ServiceRequestStatus.OUVERTE,
) -> ServiceRequest:
    request = await make_service_request(db_session, client=client, trade=trade)
    request.status = status
    await db_session.flush()
    return request


async def _cancel(http: AsyncClient, request: ServiceRequest, user: User) -> Response:
    return await http.post(f"/api/v1/requests/{request.id}/cancel", headers=_auth(user))


async def test_a_client_cancels_an_open_request_which_stays_in_history(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    request = await _request(db_session, client=client, trade=trade)

    async with _client() as http:
        response = await _cancel(http, request, client)
        mine = await http.get("/api/v1/requests/me", headers=_auth(client))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "annulee"
    await db_session.refresh(request)
    assert request.status is ServiceRequestStatus.ANNULEE
    # Jamais supprimée : toujours listée, avec son statut.
    statuses = {item["id"]: item["status"] for item in mine.json()["items"]}
    assert statuses[str(request.id)] == "annulee"


@pytest.mark.parametrize(
    "status",
    [
        ServiceRequestStatus.EN_RELATION,
        ServiceRequestStatus.CONVERTIE,
        ServiceRequestStatus.ANNULEE,
        ServiceRequestStatus.EXPIREE,
    ],
)
async def test_only_an_open_request_can_be_cancelled(
    db_session: AsyncSession, status: ServiceRequestStatus
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    request = await _request(db_session, client=client, trade=trade, status=status)

    async with _client() as http:
        response = await _cancel(http, request, client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEMANDE_NON_ANNULABLE"
    await db_session.refresh(request)
    assert request.status is status


async def test_nobody_else_can_cancel_a_request(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.CLIENT)
    other_client = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_user(db_session, role=Role.ARTISAN)
    request = await _request(db_session, client=owner, trade=trade)

    async with _client() as http:
        by_other = await _cancel(http, request, other_client)
        by_artisan = await _cancel(http, request, artisan)
        anonymous = await http.post(f"/api/v1/requests/{request.id}/cancel")
        missing = await http.post(
            "/api/v1/requests/00000000-0000-4000-8000-000000000000/cancel", headers=_auth(owner)
        )

    assert by_other.status_code == 403
    assert by_artisan.status_code == 403
    assert anonymous.status_code == 401
    assert missing.status_code == 404
    await db_session.refresh(request)
    assert request.status is ServiceRequestStatus.OUVERTE


async def test_a_cancelled_request_can_no_longer_reach_an_artisan(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, service_radius_m=10_000)
    for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
        await make_verification(
            db_session, artisan=artisan, doc_type=doc_type, status=VerificationStatus.APPROVED
        )
    await make_commission_rate(db_session, trade_id=trade.id)
    request = await _request(db_session, client=client, trade=trade)

    async with _client() as http:
        await _cancel(http, request, client)
        eligibility = await http.get(
            "/api/v1/requests/me/eligibility",
            params={"artisan_id": str(artisan.id)},
            headers=_auth(client),
        )
        sent = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth(client),
        )

    assert eligibility.json() == []
    assert sent.status_code == 409
    assert sent.json()["error"]["code"] == "DEMANDE_NON_OUVERTE"
