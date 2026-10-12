"""Les actions admin existantes (documents, litiges) et le bootstrap CLI sont
désormais journalisées — dans la même transaction que l'action."""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.audit import AuditLog
from app.models.enums import (
    AuditAction,
    AuditTargetType,
    InterventionStatus,
    Role,
    VerificationDocType,
    VerificationStatus,
)
from app.models.intervention import InterventionDispute
from app.models.user import User
from scripts.create_admin import promote_to_admin
from tests.factories import make_artisan_profile, make_engagement, make_user, make_verification


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


async def _entries_for(db_session: AsyncSession, target_id: object) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.target_id == target_id)
    return list((await db_session.execute(stmt)).scalars().all())


@pytest.mark.parametrize(
    ("path", "body", "action"),
    [
        ("approve", None, AuditAction.VERIFICATION_APPROVE),
        ("reject", {"note": "Photo illisible."}, AuditAction.VERIFICATION_REJECT),
    ],
)
async def test_a_document_decision_is_journaled(
    db_session: AsyncSession, path: str, body: dict[str, str] | None, action: AuditAction
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")
    artisan = await make_artisan_profile(db_session)
    document = await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.PENDING,
    )

    async with _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{document.id}/{path}",
            json=body,
            headers=_auth(admin),
        )

    assert response.status_code == 200, response.text
    (entry,) = await _entries_for(db_session, document.id)
    assert entry.action is action
    assert entry.target_type is AuditTargetType.VERIFICATION
    assert entry.actor_id == admin.id
    assert entry.actor_name == "Awa Admin"
    assert entry.details["doc_type"] == "cni"
    assert entry.details["artisan_id"] == str(artisan.id)


async def test_a_refused_decision_is_not_journaled(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    artisan = await make_artisan_profile(db_session)
    already = await make_verification(
        db_session, artisan=artisan, status=VerificationStatus.APPROVED
    )

    async with _client() as http:
        response = await http.post(
            f"/api/v1/admin/verifications/{already.id}/approve", headers=_auth(admin)
        )

    assert response.status_code == 409
    assert await _entries_for(db_session, already.id) == []


async def test_a_dispute_ruling_is_journaled(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    engagement = await make_engagement(db_session, status=InterventionStatus.LITIGE)
    db_session.add(
        InterventionDispute(
            intervention_id=engagement.intervention.id,
            opened_by_id=engagement.client.id,
            opened_by_role=Role.CLIENT,
            reason="Travaux non terminés.",
        )
    )
    await db_session.flush()

    async with _client() as http:
        response = await http.post(
            f"/api/v1/admin/disputes/{engagement.intervention.id}/resolve",
            json={"outcome": "rembourse", "note": "Travaux non réalisés."},
            headers=_auth(admin),
        )

    assert response.status_code == 200, response.text
    (entry,) = await _entries_for(db_session, engagement.intervention.id)
    assert entry.action is AuditAction.DISPUTE_RESOLVE
    assert entry.details["outcome"] == "rembourse"
    assert entry.details["note"] == "Travaux non réalisés."
    assert entry.details["opened_by"] == "client"


async def test_the_cli_bootstrap_is_journaled_without_an_app_actor(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    await promote_to_admin(db_session, user.phone)
    await promote_to_admin(db_session, user.phone)  # idempotent : rien de plus

    (entry,) = await _entries_for(db_session, user.id)
    assert entry.action is AuditAction.ADMIN_BOOTSTRAP
    assert entry.actor_id is None
    assert entry.details == {"previous_role": "client", "via": "scripts/create_admin.py"}
