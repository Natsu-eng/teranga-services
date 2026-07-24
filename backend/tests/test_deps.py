import uuid

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    NonAuthentifieError,
    RoleInsuffisantError,
    get_current_user,
    get_current_user_optional,
    require_role,
)
from app.core.security import TokenInvalideError, encode_access_token, encode_refresh_token
from app.models.enums import Role
from tests.factories import make_user


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_get_current_user_returns_user_for_valid_access_token(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    token = encode_access_token(user)

    resolved = await get_current_user(credentials=_bearer(token), session=db_session)

    assert resolved.id == user.id


async def test_get_current_user_rejects_missing_credentials(db_session: AsyncSession) -> None:
    with pytest.raises(NonAuthentifieError):
        await get_current_user(credentials=None, session=db_session)


async def test_get_current_user_rejects_refresh_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    refresh = encode_refresh_token(user, jti=uuid.uuid4())

    with pytest.raises(TokenInvalideError):
        await get_current_user(credentials=_bearer(refresh), session=db_session)


async def test_get_current_user_rejects_unknown_user_id(db_session: AsyncSession) -> None:
    ghost = await make_user(db_session)
    token = encode_access_token(ghost)
    await db_session.delete(ghost)
    await db_session.flush()

    with pytest.raises(TokenInvalideError):
        await get_current_user(credentials=_bearer(token), session=db_session)


async def test_get_current_user_optional_returns_none_without_credentials(
    db_session: AsyncSession,
) -> None:
    assert await get_current_user_optional(credentials=None, session=db_session) is None


async def test_get_current_user_optional_returns_user_with_credentials(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    token = encode_access_token(user)

    resolved = await get_current_user_optional(credentials=_bearer(token), session=db_session)

    assert resolved is not None
    assert resolved.id == user.id


async def test_require_role_allows_matching_role(db_session: AsyncSession) -> None:
    artisan = await make_user(db_session, role=Role.ARTISAN)

    dependency = require_role(Role.ARTISAN, Role.ADMIN)
    resolved = await dependency(artisan)

    assert resolved.id == artisan.id


async def test_require_role_rejects_non_matching_role(db_session: AsyncSession) -> None:
    client = await make_user(db_session, role=Role.CLIENT)

    dependency = require_role(Role.ARTISAN, Role.ADMIN)
    with pytest.raises(RoleInsuffisantError):
        await dependency(client)
