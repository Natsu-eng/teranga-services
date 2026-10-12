"""Expiration des demandes restées ouvertes trop longtemps (sans artisan).

La règle s'applique d'office (lecture, éligibilité, envoi) sans dépendre du
script ; `scripts/expire_requests.py` ne fait que l'enregistrer en base.
"""

from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role, ServiceRequestStatus, VerificationDocType, VerificationStatus
from app.models.request import ServiceRequest
from app.models.trade import Trade
from app.models.user import User
from app.services import requests as requests_service
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_service_request,
    make_trade,
    make_user,
    make_verification,
)

TTL_DAYS = get_settings().request_open_ttl_days


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
    age_days: float,
    status: ServiceRequestStatus = ServiceRequestStatus.OUVERTE,
) -> ServiceRequest:
    request = await make_service_request(db_session, client=client, trade=trade)
    request.status = status
    request.created_at = datetime.now(UTC) - timedelta(days=age_days)
    await db_session.flush()
    return request


async def _verified_artisan(db_session: AsyncSession, trade: Trade) -> ArtisanProfile:
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, service_radius_m=10_000)
    for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
        await make_verification(
            db_session, artisan=artisan, doc_type=doc_type, status=VerificationStatus.APPROVED
        )
    await make_commission_rate(db_session, trade_id=trade.id)
    return artisan


async def test_an_old_open_request_is_shown_expired_even_without_the_script(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    fresh = await _request(db_session, client=client, trade=trade, age_days=1)
    stale = await _request(db_session, client=client, trade=trade, age_days=TTL_DAYS + 1)

    async with _client() as http:
        body = (await http.get("/api/v1/requests/me", headers=_auth(client))).json()

    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[str(stale.id)]["status"] == "expiree"
    assert by_id[str(stale.id)]["expires_at"] is None
    assert by_id[str(fresh.id)]["status"] == "ouverte"
    # Transparence : la demande ouverte dit quand elle expirera.
    expires_at = datetime.fromisoformat(by_id[str(fresh.id)]["expires_at"])
    assert expires_at == fresh.created_at + timedelta(days=TTL_DAYS)


async def test_an_expired_request_is_neither_proposed_nor_sendable(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan = await _verified_artisan(db_session, trade)
    stale = await _request(db_session, client=client, trade=trade, age_days=TTL_DAYS + 1)

    async with _client() as http:
        eligibility = await http.get(
            "/api/v1/requests/me/eligibility",
            params={"artisan_id": str(artisan.id)},
            headers=_auth(client),
        )
        sent = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(stale.id), "artisan_id": str(artisan.id)},
            headers=_auth(client),
        )

    assert eligibility.json() == []
    assert sent.status_code == 409
    assert sent.json()["error"]["code"] == "DEMANDE_EXPIREE"


async def test_an_expired_request_can_still_be_cancelled_by_its_client(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    stale = await _request(db_session, client=client, trade=trade, age_days=TTL_DAYS + 1)

    async with _client() as http:
        response = await http.post(f"/api/v1/requests/{stale.id}/cancel", headers=_auth(client))

    assert response.status_code == 200
    assert response.json()["status"] == "annulee"


async def test_the_script_records_expiry_only_for_stale_open_requests(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    stale = await _request(db_session, client=client, trade=trade, age_days=TTL_DAYS + 1)
    fresh = await _request(db_session, client=client, trade=trade, age_days=TTL_DAYS - 1)
    in_progress = await _request(
        db_session,
        client=client,
        trade=trade,
        age_days=TTL_DAYS + 10,
        status=ServiceRequestStatus.EN_RELATION,
    )
    settings = get_settings()

    first = await requests_service.expire_stale_requests(db_session, settings=settings)
    second = await requests_service.expire_stale_requests(db_session, settings=settings)

    assert first >= 1
    assert second == 0  # idempotent
    for request, expected in (
        (stale, ServiceRequestStatus.EXPIREE),
        (fresh, ServiceRequestStatus.OUVERTE),
        (in_progress, ServiceRequestStatus.EN_RELATION),
    ):
        await db_session.refresh(request)
        assert request.status is expected
