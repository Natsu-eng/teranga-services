"""Gestion des artisans par l'admin : liste, détail, suspension (BUILD_PLAN.md §3.6).

Suspendu = invisible en recherche, fiche publique introuvable, inéligible
aux nouvelles demandes ; ses interventions en cours continuent.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.audit import AuditLog
from app.models.enums import (
    ArtisanVerifiedStatus,
    AuditAction,
    InterventionStatus,
    Role,
    ServiceRequestStatus,
    VerificationDocType,
    VerificationStatus,
)
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_engagement,
    make_service_request,
    make_trade,
    make_user,
    make_verification,
)


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Iterator[None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_session_factory] = lambda: _scope
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _verified_artisan(
    db_session: AsyncSession, trade: Trade, *, name: str
) -> tuple[User, ArtisanProfile]:
    artisan_user = await make_user(db_session, role=Role.ARTISAN, full_name=name)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, service_radius_m=10_000)
    for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
        await make_verification(
            db_session, artisan=artisan, doc_type=doc_type, status=VerificationStatus.APPROVED
        )
    return artisan_user, artisan


async def _suspend(http: AsyncClient, admin: User, artisan: ArtisanProfile) -> Response:
    return await http.post(
        f"/api/v1/admin/artisans/{artisan.id}/suspend",
        json={"reason": "Plusieurs plaintes de clients vérifiées."},
        headers=_auth(admin),
    )


async def test_a_suspended_artisan_disappears_from_search_and_public_profile(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    artisan_user, artisan = await _verified_artisan(db_session, trade, name="Moussa Suspendu")

    async with _client() as http:
        before = await http.get("/api/v1/artisans", params={"q": "Moussa Suspendu"})
        public_before = await http.get(f"/api/v1/artisans/{artisan.id}")
        suspended = await _suspend(http, admin, artisan)
        after = await http.get("/api/v1/artisans", params={"q": "Moussa Suspendu"})
        public = await http.get(f"/api/v1/artisans/{artisan.id}")
        as_owner = await http.get(f"/api/v1/artisans/{artisan.id}", headers=_auth(artisan_user))
        as_admin = await http.get(f"/api/v1/artisans/{artisan.id}", headers=_auth(admin))

    assert [item["id"] for item in before.json()["items"]] == [str(artisan.id)]
    assert public_before.json()["suspension_reason"] is None
    assert suspended.status_code == 200, suspended.text
    assert after.json()["items"] == []
    assert public.status_code == 404
    # L'artisan voit sa fiche, qu'il est suspendu, et pourquoi (transparence).
    assert as_owner.status_code == 200
    assert as_owner.json()["is_suspended"] is True
    assert as_owner.json()["suspension_reason"] == "Plusieurs plaintes de clients vérifiées."
    assert as_admin.status_code == 200


async def test_a_suspended_artisan_receives_no_new_request_but_ongoing_work_continues(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _, artisan = await _verified_artisan(db_session, trade, name="Idrissa")
    await make_commission_rate(db_session, trade_id=trade.id)
    client = await make_user(db_session, role=Role.CLIENT)
    request = await make_service_request(db_session, client=client, trade=trade)
    request.status = ServiceRequestStatus.OUVERTE
    ongoing = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    ongoing.intervention.artisan_id = artisan.id
    await db_session.flush()

    async with _client() as http:
        await _suspend(http, admin, artisan)
        coverage = await http.get(
            f"/api/v1/artisans/{artisan.id}/coverage",
            params={"trade": trade.code, "lat": 14.6937, "lng": -17.4441},
        )
        new_request = await http.post(
            "/api/v1/interventions",
            json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
            headers=_auth(client),
        )
        completed = await http.post(
            f"/api/v1/interventions/{ongoing.intervention.id}/complete",
            headers=_auth(ongoing.client),
        )

    # Lecture publique : raison neutre, jamais le motif de la suspension.
    assert coverage.json() == {"eligible": False, "reason": "artisan_indisponible"}
    assert new_request.status_code == 422
    assert new_request.json()["error"]["code"] == "ARTISAN_INDISPONIBLE"
    assert completed.status_code == 200, completed.text


async def test_suspension_needs_a_reason_and_is_journaled_then_reversible(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")
    _, artisan = await _verified_artisan(db_session, trade, name="Cheikh Réactivé")

    async with _client() as http:
        no_reason = await http.post(
            f"/api/v1/admin/artisans/{artisan.id}/suspend",
            json={"reason": "Court"},
            headers=_auth(admin),
        )
        await _suspend(http, admin, artisan)
        twice = await _suspend(http, admin, artisan)
        reactivated = await http.post(
            f"/api/v1/admin/artisans/{artisan.id}/reactivate",
            json={"note": "Échange avec l'artisan, situation régularisée."},
            headers=_auth(admin),
        )
        again = await http.post(
            f"/api/v1/admin/artisans/{artisan.id}/reactivate", json={}, headers=_auth(admin)
        )
        search = await http.get("/api/v1/artisans", params={"q": "Cheikh Réactivé"})

    assert no_reason.status_code == 422
    assert twice.status_code == 409
    assert reactivated.status_code == 200
    detail = reactivated.json()
    assert detail["is_suspended"] is False
    assert [entry["action"] for entry in detail["history"]][:2] == [
        "artisan.reactivate",
        "artisan.suspend",
    ]
    assert again.status_code == 409
    assert [item["id"] for item in search.json()["items"]] == [str(artisan.id)]

    entries = (
        (await db_session.execute(select(AuditLog).where(AuditLog.target_id == artisan.id)))
        .scalars()
        .all()
    )
    actions = {entry.action for entry in entries}
    assert actions == {AuditAction.ARTISAN_SUSPEND, AuditAction.ARTISAN_REACTIVATE}
    suspend_entry = next(e for e in entries if e.action is AuditAction.ARTISAN_SUSPEND)
    assert suspend_entry.actor_id == admin.id
    assert suspend_entry.details == {"reason": "Plusieurs plaintes de clients vérifiées."}


async def test_admins_list_artisans_by_status_and_search(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)
    _, verified = await _verified_artisan(db_session, trade, name="Zz Liste Vérifié")
    pending_user = await make_user(db_session, role=Role.ARTISAN, full_name="Zz Liste Attente")
    pending = await make_artisan_profile(db_session, user=pending_user)
    pending.verified_status = ArtisanVerifiedStatus.PENDING
    await make_verification(db_session, artisan=pending, status=VerificationStatus.PENDING)
    await db_session.flush()

    async with _client() as http:
        await _suspend(http, admin, verified)
        by_name = await http.get(
            "/api/v1/admin/artisans", params={"q": "Zz Liste"}, headers=_auth(admin)
        )
        suspended = await http.get(
            "/api/v1/admin/artisans",
            params={"status": "suspended", "q": "Zz Liste"},
            headers=_auth(admin),
        )
        waiting = await http.get(
            "/api/v1/admin/artisans",
            params={"status": "pending", "q": "Zz Liste"},
            headers=_auth(admin),
        )
        wildcard = await http.get("/api/v1/admin/artisans", params={"q": "%"}, headers=_auth(admin))

    assert {item["id"] for item in by_name.json()["items"]} == {str(verified.id), str(pending.id)}
    assert [item["id"] for item in suspended.json()["items"]] == [str(verified.id)]
    (waiting_item,) = waiting.json()["items"]
    assert waiting_item["id"] == str(pending.id)
    assert waiting_item["pending_documents"] == 1
    # « % » est cherché littéralement, jamais comme joker.
    wildcard_ids = {item["id"] for item in wildcard.json()["items"]}
    assert str(verified.id) not in wildcard_ids
    assert str(pending.id) not in wildcard_ids


async def test_artisan_management_is_reserved_to_admins(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan_user, artisan = await _verified_artisan(db_session, trade, name="Protégé")

    async with _client() as http:
        responses = [
            await http.get("/api/v1/admin/artisans", headers=_auth(client)),
            await http.get(f"/api/v1/admin/artisans/{artisan.id}", headers=_auth(client)),
            await _suspend(http, client, artisan),
            await _suspend(http, artisan_user, artisan),
            await http.post(
                f"/api/v1/admin/artisans/{artisan.id}/reactivate",
                json={},
                headers=_auth(artisan_user),
            ),
        ]

    assert [r.status_code for r in responses] == [403] * 5
    await db_session.refresh(artisan)
    assert artisan.suspended_at is None
