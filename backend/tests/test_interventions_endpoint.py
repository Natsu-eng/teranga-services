"""Test d'intégration de `/api/v1/interventions` (BUILD_PLAN.md §2.2, §3.2,
§6, §7 Lot 12) -- la mise en relation, avec commission figée à la création.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import (
    Role,
    ServiceRequestStatus,
    VerificationDocType,
    VerificationStatus,
)
from app.models.messaging import Conversation
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


async def _open_request(db_session: AsyncSession, *, client: User, trade: Trade) -> ServiceRequest:
    request = await make_service_request(db_session, client=client, trade=trade)
    request.status = ServiceRequestStatus.OUVERTE
    await db_session.flush()
    return request


async def _verified_artisan(
    db_session: AsyncSession, *, trade: Trade
) -> tuple[User, ArtisanProfile]:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
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
    return artisan_user, artisan


async def test_create_intervention_nominal_freezes_commission_rate(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    artisan_user, artisan = await _verified_artisan(db_session, trade=trade)
    await make_commission_rate(db_session, trade_id=trade.id, rate_bps=1234)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "proposee"
    assert body["commission_rate_bps"] == 1234
    assert body["client_id"] == str(client_user.id)
    assert body["artisan_id"] == str(artisan.id)
    assert body["service_request"]["status"] == "en_relation"

    await db_session.refresh(request)
    assert request.status is ServiceRequestStatus.EN_RELATION


async def test_create_intervention_opens_its_conversation(db_session: AsyncSession) -> None:
    """La messagerie naît avec l'engagement (même transaction) : le fil
    existe dès la création, entre ce client et le COMPTE de cet artisan, et
    son identifiant est exposé — dans la création comme dans la liste."""
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    artisan_user, artisan = await _verified_artisan(db_session, trade=trade)
    await make_commission_rate(db_session, trade_id=trade.id)

    async with await _client() as http:
        created = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        listed = await http.get("/api/v1/interventions/me", headers=_auth_headers(artisan_user))

    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]
    assert conversation_id is not None
    assert listed.json()["items"][0]["conversation_id"] == conversation_id

    conversation = await db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None
    assert conversation.intervention_id == uuid.UUID(created.json()["id"])
    assert conversation.client_id == client_user.id
    assert conversation.artisan_id == artisan_user.id


async def test_commission_rate_is_frozen_and_unaffected_by_later_changes(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    artisan_user, artisan = await _verified_artisan(db_session, trade=trade)
    initial_rate = await make_commission_rate(db_session, trade_id=trade.id, rate_bps=1000)

    async with await _client() as http:
        create_response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        assert create_response.status_code == 201
        intervention_id = create_response.json()["id"]
        assert create_response.json()["commission_rate_bps"] == 1000

        # Le taux change ensuite pour ce même métier -- l'intervention déjà
        # créée doit rester figée sur l'ancien taux (BUILD_PLAN.md §2.2, §7).
        initial_rate.effective_to = datetime.now(UTC)
        await db_session.flush()
        await make_commission_rate(db_session, trade_id=trade.id, rate_bps=500)

        refetch_response = await http.get(
            f"/api/v1/interventions/{intervention_id}", headers=_auth_headers(client_user)
        )

    assert refetch_response.status_code == 200
    assert refetch_response.json()["commission_rate_bps"] == 1000


async def test_create_intervention_rejects_someone_elses_request(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    owner = await make_user(db_session, role=Role.CLIENT)
    someone_else = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=owner, trade=trade)
    _artisan_user, artisan = await _verified_artisan(db_session, trade=trade)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(someone_else),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DEMANDE_AUTRUI_INTERDITE"


async def test_create_intervention_rejects_non_open_request(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    # `make_service_request` crée par défaut une demande `convertie`, pas `ouverte`.
    request = await make_service_request(db_session, client=client_user, trade=trade)
    _artisan_user, artisan = await _verified_artisan(db_session, trade=trade)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEMANDE_NON_OUVERTE"


async def test_create_intervention_rejects_unverified_artisan(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    # Artisan sans aucune ligne `verification` -> verified_status dérivé NONE.
    artisan = await make_artisan_profile(db_session)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ARTISAN_NON_VERIFIE"


async def test_create_intervention_rejects_artisan_not_exercising_the_trade(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session, code="plomberie")
    other_trade = await make_trade(db_session, code="electricite")
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    _artisan_user, artisan = await _verified_artisan(db_session, trade=other_trade)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ARTISAN_METIER_NON_EXERCE"


async def test_create_intervention_rejects_artisan_out_of_zone(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    # Demande au Plateau, Dakar (coordonnées par défaut de la factory).
    request = await _open_request(db_session, client=client_user, trade=trade)

    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    # Artisan basé à Lagos -- hors de tout rayon de service raisonnable.
    artisan = await make_artisan_profile(db_session, user=artisan_user, lat=6.5244, lng=3.3792)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, service_radius_m=5_000)
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

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ARTISAN_HORS_ZONE"


async def test_create_intervention_requires_client_role(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    request_owner = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=request_owner, trade=trade)
    _other_artisan_user, artisan = await _verified_artisan(db_session, trade=trade)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_list_my_interventions_isolates_client_and_artisan_views(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client_a = await make_user(db_session, role=Role.CLIENT)
    client_b = await make_user(db_session, role=Role.CLIENT)
    artisan_a_user, artisan_a = await _verified_artisan(db_session, trade=trade)
    artisan_b_user, artisan_b = await _verified_artisan(db_session, trade=trade)
    await make_commission_rate(db_session, trade_id=trade.id)

    request_a = await _open_request(db_session, client=client_a, trade=trade)
    request_b = await _open_request(db_session, client=client_b, trade=trade)

    async with await _client() as http:
        create_a = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request_a.id), "artisan_id": str(artisan_a.id)},
            headers=_auth_headers(client_a),
        )
        create_b = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request_b.id), "artisan_id": str(artisan_b.id)},
            headers=_auth_headers(client_b),
        )
        assert create_a.status_code == 201
        assert create_b.status_code == 201
        intervention_a_id = create_a.json()["id"]
        intervention_b_id = create_b.json()["id"]

        client_a_view = await http.get("/api/v1/interventions/me", headers=_auth_headers(client_a))
        artisan_a_view = await http.get(
            "/api/v1/interventions/me", headers=_auth_headers(artisan_a_user)
        )

    client_a_ids = {item["id"] for item in client_a_view.json()["items"]}
    artisan_a_ids = {item["id"] for item in artisan_a_view.json()["items"]}

    assert client_a_ids == {intervention_a_id}
    assert artisan_a_ids == {intervention_a_id}
    assert intervention_b_id not in client_a_ids
    assert intervention_b_id not in artisan_a_ids


async def test_get_intervention_by_unrelated_user_is_forbidden(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client_user = await make_user(db_session, role=Role.CLIENT)
    request = await _open_request(db_session, client=client_user, trade=trade)
    _artisan_user, artisan = await _verified_artisan(db_session, trade=trade)
    await make_commission_rate(db_session, trade_id=trade.id)
    stranger = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        create_response = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        intervention_id = create_response.json()["id"]

        response = await http.get(
            f"/api/v1/interventions/{intervention_id}", headers=_auth_headers(stranger)
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INTERVENTION_ACCES_INTERDIT"


async def test_get_unknown_intervention_returns_404(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        response = await http.get(
            "/api/v1/interventions/00000000-0000-0000-0000-000000000000",
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INTERVENTION_NOT_FOUND"
