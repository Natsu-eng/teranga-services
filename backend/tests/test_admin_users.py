"""Gestion du rôle admin depuis le back-office (BUILD_PLAN.md §3.6).

ANTI-VERROUILLAGE (non négociable) : impossible de retirer le DERNIER admin,
impossible de retirer son PROPRE rôle. Chaque octroi/retrait est journalisé
et prend effet immédiatement (le rôle est relu en base à chaque requête).
"""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.audit import AuditLog
from app.models.enums import AuditAction, Role
from app.models.user import User
from app.services import admin_users as admin_users_service
from app.services.admin_users import DernierAdminError
from tests.factories import make_artisan_profile, make_user


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


async def _grant(http: AsyncClient, admin: User, target: User) -> Response:
    return await http.post(
        f"/api/v1/admin/users/{target.id}/grant-admin",
        json={"note": "Renfort de l'équipe support."},
        headers=_auth(admin),
    )


async def _revoke(http: AsyncClient, admin: User, target: User) -> Response:
    return await http.post(
        f"/api/v1/admin/users/{target.id}/revoke-admin", json={}, headers=_auth(admin)
    )


async def _only_admin(db_session: AsyncSession, *, full_name: str = "Seul Admin") -> User:
    """Un admin qui est le SEUL admin actif. Les tests partagent la base de
    dev : les autres admins sont rétrogradés DANS la transaction du test,
    annulée à la fin — rien n'est modifié durablement."""
    await db_session.execute(update(User).where(User.role == Role.ADMIN).values(role=Role.CLIENT))
    return await make_user(db_session, role=Role.ADMIN, full_name=full_name)


async def _audit(db_session: AsyncSession, target: User) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.target_id == target.id).order_by(AuditLog.created_at)
    return list((await db_session.execute(stmt)).scalars())


async def test_an_admin_cannot_revoke_their_own_role(db_session: AsyncSession) -> None:
    # Même avec d'autres admins présents : son propre rôle, jamais.
    admin = await make_user(db_session, role=Role.ADMIN)
    await make_user(db_session, role=Role.ADMIN)

    async with _client() as http:
        response = await _revoke(http, admin, admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVOCATION_DE_SOI_INTERDITE"
    await db_session.refresh(admin)
    assert admin.role is Role.ADMIN
    assert await _audit(db_session, admin) == []


async def test_the_last_admin_can_never_be_revoked(db_session: AsyncSession) -> None:
    first = await _only_admin(db_session, full_name="Admin Fondateur")
    candidate = await make_user(db_session, role=Role.CLIENT, full_name="Admin Second")

    async with _client() as http:
        granted = await _grant(http, first, candidate)
        # Deux admins : le second retire le premier (autorisé)...
        revoked = await _revoke(http, candidate, first)
        # ...puis le premier, redevenu client, ne peut plus rien faire.
        lost_access = await _revoke(http, first, candidate)
        # Le second est désormais le DERNIER : il ne peut se retirer (soi),
        # et personne d'autre ne peut le retirer non plus.
        self_revoke = await _revoke(http, candidate, candidate)
        listed = await http.get(
            "/api/v1/admin/users", params={"q": "Admin Second"}, headers=_auth(candidate)
        )

    assert granted.status_code == 200, granted.text
    assert granted.json()["role"] == "admin"
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["role"] == "client"
    assert lost_access.status_code == 403
    assert self_revoke.json()["error"]["code"] == "REVOCATION_DE_SOI_INTERDITE"
    (row,) = listed.json()["items"]
    assert row["is_self"] is True
    assert row["can_revoke_admin"] is False
    assert row["guard"] is not None


async def test_crossed_revocations_cannot_empty_the_back_office(
    db_session: AsyncSession,
) -> None:
    """Course : A et B, seuls admins, se retirent mutuellement en même temps.
    Les deux requêtes passent l'authentification (rôle admin à cet instant) ;
    la première qui obtient le verrou retire l'autre. La seconde, sous
    verrou, recompte les admins : il n'en reste qu'un, sa cible -> refus
    DERNIER_ADMIN. Le back-office garde toujours un admin."""
    a = await _only_admin(db_session, full_name="Admin A")
    b = await make_user(db_session, role=Role.ADMIN, full_name="Admin B")

    # Requête de B, verrou obtenu en premier : A est retiré.
    await admin_users_service.revoke_admin(db_session, admin=b, user_id=a.id, note=None)
    # Requête de A, authentifiée AVANT ce retrait, qui arrive au verrou ensuite.
    with pytest.raises(DernierAdminError):
        await admin_users_service.revoke_admin(db_session, admin=a, user_id=b.id, note=None)

    await db_session.refresh(b)
    assert b.role is Role.ADMIN
    remaining = (
        (await db_session.execute(select(User.id).where(User.role == Role.ADMIN))).scalars().all()
    )
    assert list(remaining) == [b.id]


async def test_revocation_takes_effect_immediately(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    other = await make_user(db_session, role=Role.ADMIN)
    token = _auth(other)  # jeton émis AVANT le retrait

    async with _client() as http:
        before = await http.get("/api/v1/admin/overview", headers=token)
        revoked = await _revoke(http, admin, other)
        after = await http.get("/api/v1/admin/overview", headers=token)

    assert before.status_code == 200
    assert revoked.status_code == 200
    # Même jeton, encore valide : le rôle est relu en base, l'accès est coupé.
    assert after.status_code == 403


async def test_an_artisan_account_cannot_be_promoted(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    artisan_user = await make_user(db_session, role=Role.ARTISAN, full_name="Zz Artisan Promu")
    await make_artisan_profile(db_session, user=artisan_user)
    # Un client qui a un profil artisan (cas limite) reste lui aussi refusé.
    hybrid = await make_user(db_session, role=Role.CLIENT, full_name="Zz Hybride")
    await make_artisan_profile(db_session, user=hybrid)

    async with _client() as http:
        artisan_attempt = await _grant(http, admin, artisan_user)
        hybrid_attempt = await _grant(http, admin, hybrid)
        listed = await http.get("/api/v1/admin/users", params={"q": "Zz "}, headers=_auth(admin))

    for response in (artisan_attempt, hybrid_attempt):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "COMPTE_ARTISAN_NON_PROMOUVABLE"
    rows = {row["full_name"]: row for row in listed.json()["items"]}
    assert rows["Zz Artisan Promu"]["can_grant_admin"] is False
    assert rows["Zz Hybride"]["has_artisan_profile"] is True
    assert rows["Zz Hybride"]["guard"] is not None
    await db_session.refresh(artisan_user)
    assert artisan_user.role is Role.ARTISAN


async def test_revoking_restores_the_role_deduced_from_data(db_session: AsyncSession) -> None:
    # Un admin qui possède un profil artisan (historique) redevient artisan.
    admin = await make_user(db_session, role=Role.ADMIN)
    with_profile = await make_user(db_session, role=Role.ADMIN)
    await make_artisan_profile(db_session, user=with_profile)

    async with _client() as http:
        response = await _revoke(http, admin, with_profile)

    assert response.json()["role"] == "artisan"


async def test_grant_and_revoke_are_journaled_and_idempotency_is_refused(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")
    target = await make_user(db_session, role=Role.CLIENT)

    async with _client() as http:
        await _grant(http, admin, target)
        twice = await _grant(http, admin, target)
        await _revoke(http, admin, target)
        not_admin = await _revoke(http, admin, target)
        journal = await http.get(
            "/api/v1/admin/audit",
            params={"target_type": "user", "target_id": str(target.id)},
            headers=_auth(admin),
        )

    assert twice.json()["error"]["code"] == "DEJA_ADMIN"
    assert not_admin.json()["error"]["code"] == "PAS_ADMIN"
    entries = await _audit(db_session, target)
    # Une ligne par action réussie, aucune pour les refus.
    assert [e.action for e in entries] == [
        AuditAction.USER_GRANT_ADMIN,
        AuditAction.USER_REVOKE_ADMIN,
    ]
    assert all(e.actor_id == admin.id and e.actor_name == "Awa Admin" for e in entries)
    assert entries[0].details == {"previous_role": "client", "note": "Renfort de l'équipe support."}
    assert entries[1].details == {"restored_role": "client", "note": None}
    assert journal.json()["pagination"]["total"] == 2


async def test_users_list_search_is_literal_and_filters_by_role(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    client = await make_user(db_session, role=Role.CLIENT, full_name="Yy Cliente_Test")
    await make_user(db_session, role=Role.CLIENT, full_name="Yy ClienteXTest")

    async with _client() as http:
        underscore = await http.get(
            "/api/v1/admin/users", params={"q": "Cliente_"}, headers=_auth(admin)
        )
        admins = await http.get(
            "/api/v1/admin/users", params={"role": "admin"}, headers=_auth(admin)
        )
        unknown = await http.post(
            "/api/v1/admin/users/00000000-0000-0000-0000-000000000000/grant-admin",
            json={},
            headers=_auth(admin),
        )

    # « _ » est cherché littéralement : « ClienteXTest » ne correspond pas.
    assert [row["id"] for row in underscore.json()["items"]] == [str(client.id)]
    assert {row["role"] for row in admins.json()["items"]} == {"admin"}
    assert str(admin.id) in {row["id"] for row in admins.json()["items"]}
    assert unknown.status_code == 404


async def test_user_management_is_reserved_to_admins(db_session: AsyncSession) -> None:
    client = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_user(db_session, role=Role.ARTISAN)
    admin = await make_user(db_session, role=Role.ADMIN)

    async with _client() as http:
        responses = [
            await http.get("/api/v1/admin/users", headers=_auth(client)),
            await http.get("/api/v1/admin/users", headers=_auth(artisan)),
            # Un client ne peut pas s'auto-promouvoir.
            await _grant(http, client, client),
            await _grant(http, artisan, client),
            await _revoke(http, client, admin),
        ]
        anonymous = await http.get("/api/v1/admin/users")

    assert [r.status_code for r in responses] == [403] * 5
    assert anonymous.status_code == 401
    await db_session.refresh(client)
    assert client.role is Role.CLIENT
    await db_session.refresh(admin)
    assert admin.role is Role.ADMIN
