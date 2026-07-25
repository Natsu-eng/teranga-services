"""Machine à états de `intervention` : accept/decline/complete
(BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b).

```
proposee --(artisan accepte)--> acceptee --(devis accepté)--> en_cours --(complétion)--> terminee
proposee --(artisan refuse)--> annulee
```
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import InterventionStatus, Role, ServiceRequestStatus
from app.models.intervention import Intervention
from app.models.request import ServiceRequest
from app.models.trade import Trade
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


async def _proposed_intervention(
    db_session: AsyncSession, *, trade: Trade, client: User, artisan: ArtisanProfile
) -> tuple[ServiceRequest, Intervention]:
    request = await make_service_request(db_session, client=client, trade=trade)
    request.status = ServiceRequestStatus.EN_RELATION
    await db_session.flush()
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.PROPOSEE,
    )
    return request, intervention


async def test_artisan_accepts_intervention(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    _request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/accept", headers=_auth_headers(artisan_user)
        )

    assert response.status_code == 200
    assert response.json()["status"] == "acceptee"


async def test_artisan_declines_intervention_reopens_the_request(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/decline",
            json={"reason": "Indisponible cette semaine."},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "annulee"
    assert body["decline_reason"] == "Indisponible cette semaine."

    await db_session.refresh(request)
    assert request.status is ServiceRequestStatus.OUVERTE


async def test_decline_without_a_reason_is_accepted(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    _request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/decline",
            json={},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 200
    assert response.json()["decline_reason"] is None


async def test_accept_rejects_an_unrelated_artisan(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    _request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )
    unrelated_artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=unrelated_artisan_user)

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/accept",
            headers=_auth_headers(unrelated_artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_RESERVEE_AUTRE_PARTIE"


async def test_accept_rejects_client_role(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    _request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/accept", headers=_auth_headers(client_user)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_accept_on_already_accepted_intervention_is_an_invalid_transition(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/accept", headers=_auth_headers(artisan_user)
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSITION_INTERVENTION_INVALIDE"


async def test_decline_on_accepted_intervention_is_an_invalid_transition(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.ACCEPTEE,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/decline",
            json={},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSITION_INTERVENTION_INVALIDE"


async def test_client_completes_an_in_progress_intervention(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.EN_COURS,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/complete", headers=_auth_headers(client_user)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "terminee"
    assert body["completed_at"] is not None


async def test_complete_rejects_an_unrelated_client(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    stranger = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.EN_COURS,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/complete", headers=_auth_headers(stranger)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_RESERVEE_AUTRE_PARTIE"


async def test_complete_rejects_artisan_role(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    request = await make_service_request(db_session, client=client_user, trade=trade)
    rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = await make_intervention(
        db_session,
        service_request=request,
        client=client_user,
        artisan=artisan,
        commission_rate=rate,
        status=InterventionStatus.EN_COURS,
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/complete", headers=_auth_headers(artisan_user)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_complete_on_a_proposed_intervention_is_an_invalid_transition(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_artisan_profile(db_session)
    _request, intervention = await _proposed_intervention(
        db_session, trade=trade, client=client_user, artisan=artisan
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/interventions/{intervention.id}/complete", headers=_auth_headers(client_user)
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSITION_INTERVENTION_INVALIDE"
