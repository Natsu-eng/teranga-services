"""Tests d'intégration de l'espace admin de revue des artisans (BUILD_PLAN.md,
espace admin) -- lot sensible : protection par rôle de toutes les routes
`/api/v1/admin/*`, approbation/rejet d'un document, et les deux chaînes
métier complètes (approbation -> visible + contactable ; rejet -> reste
invisible + non contactable).
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile, Verification
from app.models.enums import (
    ArtisanVerifiedStatus,
    Role,
    ServiceRequestStatus,
    VerificationDocType,
    VerificationStatus,
)
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


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _unverified_artisan_with_pending_docs(
    db_session: AsyncSession, *, trade: Trade
) -> tuple[User, ArtisanProfile, Verification, Verification]:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(
        db_session, user=artisan_user, lat=REFERENCE_LAT, lng=REFERENCE_LNG
    )
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    cni = await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.PENDING,
    )
    selfie = await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.SELFIE,
        status=VerificationStatus.PENDING,
    )
    artisan.verified_status = ArtisanVerifiedStatus.PENDING
    await db_session.flush()
    return artisan_user, artisan, cni, selfie


async def _open_request(db_session: AsyncSession, *, client: User, trade: Trade) -> ServiceRequest:
    request = await make_service_request(
        db_session, client=client, trade=trade, lat=REFERENCE_LAT, lng=REFERENCE_LNG
    )
    request.status = ServiceRequestStatus.OUVERTE
    await db_session.flush()
    return request


# --- Protection par rôle : matrice sur toutes les routes admin ------------

_ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/verifications"),
    ("POST", "/api/v1/admin/verifications/00000000-0000-0000-0000-000000000000/approve"),
    ("POST", "/api/v1/admin/verifications/00000000-0000-0000-0000-000000000000/reject"),
    ("GET", "/api/v1/admin/verifications/00000000-0000-0000-0000-000000000000/content"),
    ("GET", "/api/v1/admin/artisans/00000000-0000-0000-0000-000000000000"),
]


@pytest.mark.parametrize("method,path", _ADMIN_ROUTES)
async def test_client_cannot_access_any_admin_route(
    db_session: AsyncSession, method: str, path: str
) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)

    async with await _client() as http:
        response = await http.request(
            method,
            path,
            json={"note": "motif de test suffisamment long"},
            headers=_auth_headers(client_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


@pytest.mark.parametrize("method,path", _ADMIN_ROUTES)
async def test_artisan_cannot_access_any_admin_route(
    db_session: AsyncSession, method: str, path: str
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)

    async with await _client() as http:
        response = await http.request(
            method,
            path,
            json={"note": "motif de test suffisamment long"},
            headers=_auth_headers(artisan_user),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


@pytest.mark.parametrize("method,path", _ADMIN_ROUTES)
async def test_unauthenticated_cannot_access_any_admin_route(method: str, path: str) -> None:
    async with await _client() as http:
        response = await http.request(
            method, path, json={"note": "motif de test suffisamment long"}
        )

    assert response.status_code == 401


# --- Liste de la file d'attente --------------------------------------------


async def test_admin_lists_pending_verifications(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Admin")
    artisan_user, artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.get("/api/v1/admin/verifications", headers=_auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert str(cni.id) in ids
    item = next(i for i in body["items"] if i["id"] == str(cni.id))
    assert item["artisan_id"] == str(artisan.id)
    assert item["doc_type"] == "cni"
    assert item["status"] == "pending"


async def test_admin_filters_verifications_by_status(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )
    other_artisan_user = await make_user(db_session, role=Role.ARTISAN, full_name="Other")
    other_artisan = await make_artisan_profile(db_session, user=other_artisan_user)
    approved = await make_verification(
        db_session,
        artisan=other_artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.APPROVED,
    )

    async with await _client() as http:
        response = await http.get(
            "/api/v1/admin/verifications",
            params={"status": "approved", "page_size": 50},
            headers=_auth_headers(admin),
        )

    # Inclusion, pas égalité stricte : la base de dev réelle contient déjà
    # d'autres lignes `approved` (seed.py) -- seul compte que le filtre
    # inclut bien la nôtre et exclut les deux `pending` créées ci-dessus.
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(approved.id) in ids
    assert str(cni.id) not in ids
    assert str(selfie.id) not in ids


# --- Accès au binaire du document -------------------------------------------


async def test_admin_reads_document_content(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )
    # `make_verification` pose une URL de test qui ne correspond à aucun
    # fichier réel sur disque -- ce test vérifie donc surtout que l'accès
    # est bien réservé admin (404 storage plutôt que 403/401 rôle) ; le
    # contenu binaire réel est déjà exercé côté upload, Lot B.
    admin_headers = _auth_headers(admin)

    async with await _client() as http:
        response = await http.get(
            f"/api/v1/admin/verifications/{cni.id}/content", headers=admin_headers
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERIFICATION_NOT_FOUND"


async def test_admin_content_404_for_unknown_verification(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)

    async with await _client() as http:
        response = await http.get(
            "/api/v1/admin/verifications/00000000-0000-0000-0000-000000000000/content",
            headers=_auth_headers(admin),
        )

    assert response.status_code == 404


# --- Approbation -------------------------------------------------------------


async def test_approve_sets_reviewed_by_to_current_admin_and_status_approved(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Admin Modou")
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve", headers=_auth_headers(admin)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == str(admin.id)
    assert body["reviewed_at"] is not None

    stmt = select(Verification.status, Verification.reviewed_by, Verification.reviewed_at).where(
        Verification.id == cni.id
    )
    persisted_status, persisted_reviewer, persisted_at = (await db_session.execute(stmt)).one()
    assert persisted_status == VerificationStatus.APPROVED
    assert persisted_reviewer == admin.id
    assert persisted_at is not None


async def test_reviewed_by_is_never_taken_from_the_client(db_session: AsyncSession) -> None:
    """`reviewed_by` n'est jamais un champ d'entrée -- même en essayant de
    l'injecter dans le corps de la requête, seul l'admin authentifié (JWT)
    compte."""
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    other_admin = await make_user(db_session, role=Role.ADMIN, full_name="Other Admin")
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve",
            json={"reviewed_by": str(other_admin.id)},
            headers=_auth_headers(admin),
        )

    assert response.status_code == 200
    assert response.json()["reviewed_by"] == str(admin.id)


async def test_approving_an_already_reviewed_document_is_rejected(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        first = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve", headers=_auth_headers(admin)
        )
        assert first.status_code == 200

        second = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve", headers=_auth_headers(admin)
        )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "VERIFICATION_DEJA_TRAITEE"


async def test_approving_unknown_verification_is_404(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)

    async with await _client() as http:
        response = await http.post(
            "/api/v1/admin/verifications/00000000-0000-0000-0000-000000000000/approve",
            headers=_auth_headers(admin),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERIFICATION_NOT_FOUND"


# --- Rejet -------------------------------------------------------------------


async def test_reject_requires_a_note(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/reject",
            json={},
            headers=_auth_headers(admin),
        )

    assert response.status_code == 422


async def test_reject_empty_note_is_rejected(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/reject",
            json={"note": ""},
            headers=_auth_headers(admin),
        )

    assert response.status_code == 422


async def test_reject_with_note_sets_status_and_note(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, _artisan, cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/reject",
            json={"note": "Photo illisible, merci de renvoyer un scan net."},
            headers=_auth_headers(admin),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["note"] == "Photo illisible, merci de renvoyer un scan net."
    assert body["reviewed_by"] == str(admin.id)


# --- Vue admin d'un artisan ---------------------------------------------------


async def test_admin_gets_artisan_detail_with_all_documents(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _artisan_user, artisan, _cni, _selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )

    async with await _client() as http:
        response = await http.get(
            f"/api/v1/admin/artisans/{artisan.id}", headers=_auth_headers(admin)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(artisan.id)
    assert len(body["documents"]) == 2
    assert body["verified_status"] == "pending"


# --- Chaîne complète : approbation -> visible + contactable -------------------


async def test_full_chain_approval_makes_artisan_visible_and_contactable(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan_user, artisan, cni, selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )
    await make_commission_rate(db_session, trade_id=trade.id)
    request = await _open_request(db_session, client=client_user, trade=trade)

    async with await _client() as http:
        # Avant approbation : invisible en recherche, mise en relation refusée.
        search_before = await http.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )
        assert str(artisan.id) not in [i["id"] for i in search_before.json()["items"]]

        intervention_before = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        assert intervention_before.status_code == 422
        assert intervention_before.json()["error"]["code"] == "ARTISAN_NON_VERIFIE"

        # L'admin approuve les deux documents requis.
        approve_cni = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve", headers=_auth_headers(admin)
        )
        assert approve_cni.status_code == 200
        assert (
            approve_cni.json()["artisan_verified_status"] == "pending"
        )  # selfie encore en attente

        approve_selfie = await http.post(
            f"/api/v1/admin/verifications/{selfie.id}/approve", headers=_auth_headers(admin)
        )
        assert approve_selfie.status_code == 200
        assert approve_selfie.json()["artisan_verified_status"] == "verified"

        # Après approbation complète : visible, contactable.
        search_after = await http.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )
        assert str(artisan.id) in [i["id"] for i in search_after.json()["items"]]

        intervention_after = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        assert intervention_after.status_code == 201

    stmt = select(ArtisanProfile.verified_status).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == ArtisanVerifiedStatus.VERIFIED
    assert artisan_user.role == Role.ARTISAN  # sanity : le rôle ne bouge jamais


# --- Chaîne complète : rejet -> reste invisible + non contactable -------------


async def test_full_chain_rejection_keeps_artisan_invisible_and_uncontactable(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    client_user = await make_user(db_session, role=Role.CLIENT)
    _artisan_user, artisan, cni, selfie = await _unverified_artisan_with_pending_docs(
        db_session, trade=trade
    )
    await make_commission_rate(db_session, trade_id=trade.id)
    request = await _open_request(db_session, client=client_user, trade=trade)

    async with await _client() as http:
        approve_cni = await http.post(
            f"/api/v1/admin/verifications/{cni.id}/approve", headers=_auth_headers(admin)
        )
        assert approve_cni.status_code == 200

        reject_selfie = await http.post(
            f"/api/v1/admin/verifications/{selfie.id}/reject",
            json={"note": "Selfie flou, merci de reprendre la photo."},
            headers=_auth_headers(admin),
        )
        assert reject_selfie.status_code == 200
        assert reject_selfie.json()["artisan_verified_status"] == "rejected"

        search_after = await http.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )
        assert str(artisan.id) not in [i["id"] for i in search_after.json()["items"]]

        intervention_after = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth_headers(client_user),
        )
        assert intervention_after.status_code == 422
        assert intervention_after.json()["error"]["code"] == "ARTISAN_NON_VERIFIE"

    stmt = select(ArtisanProfile.verified_status).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == ArtisanVerifiedStatus.REJECTED
