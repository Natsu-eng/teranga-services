"""Journal d'audit des actions admin (BUILD_PLAN.md §3.6).

Ajout seul, garanti par la base : aucune modification, suppression ni
vidage n'est possible, même en SQL direct.
"""

import uuid
from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditTargetType, Role
from app.models.user import User
from app.services import audit as audit_service
from tests.factories import make_user


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


async def _entry(db_session: AsyncSession, admin: User) -> AuditLog:
    return await audit_service.record(
        db_session,
        actor=admin,
        action=AuditAction.ARTISAN_SUSPEND,
        target_type=AuditTargetType.ARTISAN,
        target_id=uuid.uuid4(),
        details={"reason": "Test", "when": uuid.UUID(int=1)},
    )


async def test_an_entry_records_who_did_what_to_whom(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")

    entry = await _entry(db_session, admin)
    await db_session.refresh(entry)

    assert entry.actor_id == admin.id
    assert entry.actor_name == "Awa Admin"  # instantané du nom
    assert entry.action is AuditAction.ARTISAN_SUSPEND
    assert entry.details == {"reason": "Test", "when": str(uuid.UUID(int=1))}
    assert entry.created_at is not None


@pytest.mark.parametrize(
    "statement",
    [
        lambda entry_id: (
            update(AuditLog).where(AuditLog.id == entry_id).values(details={"reason": "réécrit"})
        ),
        lambda entry_id: delete(AuditLog).where(AuditLog.id == entry_id),
    ],
    ids=["update", "delete"],
)
async def test_the_database_refuses_any_change_or_deletion(
    db_session: AsyncSession, statement: object
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    entry = await _entry(db_session, admin)

    with pytest.raises(DBAPIError, match="ajout seul"):
        async with db_session.begin_nested():
            await db_session.execute(statement(entry.id))  # type: ignore[operator]


async def test_the_database_refuses_truncate(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="ajout seul"):
        async with db_session.begin_nested():
            await db_session.execute(text("TRUNCATE audit_log"))


async def test_admins_read_the_journal_newest_first_with_filters(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    first = await _entry(db_session, admin)
    second = await audit_service.record(
        db_session,
        actor=admin,
        action=AuditAction.REVIEW_HIDE,
        target_type=AuditTargetType.REVIEW,
        target_id=uuid.uuid4(),
    )

    async with _client() as http:
        everything = await http.get("/api/v1/admin/audit", headers=_auth(admin))
        reviews_only = await http.get(
            "/api/v1/admin/audit",
            params={"action": "review.hide", "actor_id": str(admin.id)},
            headers=_auth(admin),
        )
        one_target = await http.get(
            "/api/v1/admin/audit",
            params={"target_type": "artisan", "target_id": str(first.target_id)},
            headers=_auth(admin),
        )

    assert everything.status_code == 200, everything.text
    ids = [item["id"] for item in everything.json()["items"]]
    assert ids.index(str(second.id)) < ids.index(str(first.id))  # plus récent d'abord
    assert [item["id"] for item in reviews_only.json()["items"]] == [str(second.id)]
    assert [item["id"] for item in one_target.json()["items"]] == [str(first.id)]


async def test_the_journal_is_reserved_to_admins(db_session: AsyncSession) -> None:
    client = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_user(db_session, role=Role.ARTISAN)

    async with _client() as http:
        anonymous = await http.get("/api/v1/admin/audit")
        as_client = await http.get("/api/v1/admin/audit", headers=_auth(client))
        as_artisan = await http.get("/api/v1/admin/audit", headers=_auth(artisan))

    assert anonymous.status_code == 401
    assert as_client.status_code == 403
    assert as_artisan.status_code == 403
    assert as_client.json()["error"]["code"] == "ROLE_INSUFFISANT"


def test_no_route_can_modify_or_delete_the_journal() -> None:
    """Seule la lecture existe : le schéma OpenAPI de l'API ne déclare aucune
    autre méthode sous /admin/audit."""
    paths = {
        path: set(operations)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/admin/audit")
    }

    assert paths, "la route de lecture doit exister"
    for path, methods in paths.items():
        assert methods == {"get"}, (path, methods)
