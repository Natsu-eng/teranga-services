import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from tests.factories import make_user


async def test_refresh_token_persists_and_reads_back(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    token = RefreshToken(
        user_id=user.id,
        token_hash="hashed-token",
        jti=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent="pytest",
        ip="127.0.0.1",
    )
    db_session.add(token)
    await db_session.flush()

    read_back = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.id == token.id))
    ).scalar_one()

    assert read_back.user_id == user.id
    assert read_back.token_hash == "hashed-token"
    assert read_back.revoked_at is None


async def test_refresh_token_jti_is_unique(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    shared_jti = uuid.uuid4()
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="first",
            jti=shared_jti,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await db_session.flush()

    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="second",
            jti=shared_jti,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_refresh_token_deleted_when_user_deleted(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    token = RefreshToken(
        user_id=user.id,
        token_hash="hashed-token",
        jti=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(token)
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    remaining = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.id == token.id))
    ).scalar_one_or_none()
    assert remaining is None
