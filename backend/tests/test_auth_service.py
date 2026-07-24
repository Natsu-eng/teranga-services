import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import decode_token, encode_access_token, encode_refresh_token
from app.models.refresh_token import RefreshToken
from app.services import auth as auth_service
from tests.factories import make_user


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


async def test_issue_token_pair_persists_refresh_token_row(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()

    access, refresh = await auth_service.issue_token_pair(
        db_session, user, settings=settings, user_agent="pytest", ip="127.0.0.1"
    )

    access_payload = decode_token(access, settings=settings)
    assert access_payload["type"] == "access"
    assert access_payload["sub"] == str(user.id)

    refresh_payload = decode_token(refresh, settings=settings)
    assert refresh_payload["type"] == "refresh"

    row = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == uuid.UUID(refresh_payload["jti"]))
        )
    ).scalar_one()
    assert row.user_id == user.id
    assert row.revoked_at is None
    assert refresh not in row.token_hash


async def test_rotate_refresh_token_revokes_old_and_issues_new(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()
    _, refresh = await auth_service.issue_token_pair(db_session, user, settings=settings)
    old_jti = decode_token(refresh, settings=settings)["jti"]

    new_access, new_refresh = await auth_service.rotate_refresh_token(
        db_session, refresh, settings=settings
    )

    old_row = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.jti == uuid.UUID(old_jti)))
    ).scalar_one()
    assert old_row.revoked_at is not None

    new_payload = decode_token(new_refresh, settings=settings)
    assert new_payload["jti"] != old_jti
    new_row = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == uuid.UUID(new_payload["jti"]))
        )
    ).scalar_one()
    assert new_row.revoked_at is None

    access_payload = decode_token(new_access, settings=settings)
    assert access_payload["sub"] == str(user.id)


async def test_rotate_refresh_token_rejects_non_refresh_type(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()
    access = encode_access_token(user, settings=settings)

    with pytest.raises(auth_service.RefreshInvalideError):
        await auth_service.rotate_refresh_token(db_session, access, settings=settings)


async def test_replaying_revoked_refresh_token_revokes_entire_family(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    settings = _settings()
    _, refresh_a = await auth_service.issue_token_pair(db_session, user, settings=settings)
    _, refresh_b = await auth_service.rotate_refresh_token(db_session, refresh_a, settings=settings)

    # refresh_a est désormais révoqué (rotation) -- son rejeu doit être
    # traité comme un signal de vol : toute la famille est révoquée.
    with pytest.raises(auth_service.RefreshReutiliseError):
        await auth_service.rotate_refresh_token(db_session, refresh_a, settings=settings)

    # La session issue de la rotation légitime (refresh_b) est elle aussi
    # révoquée (famille entière) : la représenter est donc aussi traitée
    # comme un rejeu, pas seulement refresh_a.
    with pytest.raises(auth_service.RefreshReutiliseError):
        await auth_service.rotate_refresh_token(db_session, refresh_b, settings=settings)


async def test_rotate_refresh_token_rejects_unknown_jti(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()

    forged = encode_refresh_token(user, jti=uuid.uuid4(), settings=settings)

    with pytest.raises(auth_service.RefreshInvalideError):
        await auth_service.rotate_refresh_token(db_session, forged, settings=settings)


async def test_revoke_refresh_token_marks_it_revoked(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()
    _, refresh = await auth_service.issue_token_pair(db_session, user, settings=settings)
    jti = decode_token(refresh, settings=settings)["jti"]

    await auth_service.revoke_refresh_token(db_session, refresh, settings=settings)

    row = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.jti == uuid.UUID(jti)))
    ).scalar_one()
    assert row.revoked_at is not None


async def test_revoke_refresh_token_is_silent_on_garbage_input(db_session: AsyncSession) -> None:
    # Ne doit jamais lever : /logout répond 204 systématiquement, un token
    # invalide ne doit fournir aucun oracle.
    await auth_service.revoke_refresh_token(db_session, "pas-un-jwt", settings=_settings())


async def test_revoke_all_sessions_revokes_every_active_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    settings = _settings()
    _, refresh_1 = await auth_service.issue_token_pair(db_session, user, settings=settings)
    _, refresh_2 = await auth_service.issue_token_pair(db_session, user, settings=settings)

    await auth_service.revoke_all_sessions(db_session, user.id)

    for refresh in (refresh_1, refresh_2):
        jti = decode_token(refresh, settings=settings)["jti"]
        row = (
            await db_session.execute(select(RefreshToken).where(RefreshToken.jti == uuid.UUID(jti)))
        ).scalar_one()
        assert row.revoked_at is not None
