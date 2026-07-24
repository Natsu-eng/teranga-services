"""Émission et vérification des JWT (BUILD_PLAN.md §4.2).

Payload : `sub` (id utilisateur), `role`, `jti`, `iat`, `exp`, `type`
(`"access"` ou `"refresh"`) -- le claim `type` empêche qu'un refresh token
soit accepté là où un access token est attendu, et réciproquement.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict, cast

import jwt

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.user import User

# Algorithme fixé en dur, volontairement non configurable via env : le
# rendre configurable ouvrirait une attaque par confusion d'algorithme
# (ex. un attaquant qui imposerait "none" ou un algorithme asymétrique).
_ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


class TokenPayload(TypedDict):
    sub: str
    role: str
    jti: str
    iat: int
    exp: int
    type: TokenType


class TokenInvalideError(AppError):
    def __init__(self, message: str = "Session invalide ou expirée.") -> None:
        super().__init__(code="TOKEN_INVALIDE", message=message, status_code=401)


def _encode(
    user: User, *, token_type: TokenType, ttl_seconds: int, jti: uuid.UUID, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload: TokenPayload = {
        "sub": str(user.id),
        "role": user.role.value,
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "type": token_type,
    }
    return jwt.encode(dict(payload), settings.jwt_secret, algorithm=_ALGORITHM)


def encode_access_token(user: User, *, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _encode(
        user,
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
        jti=uuid.uuid4(),
        settings=settings,
    )


def encode_refresh_token(user: User, *, jti: uuid.UUID, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _encode(
        user,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
        jti=jti,
        settings=settings,
    )


def decode_token(token: str, *, settings: Settings | None = None) -> TokenPayload:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenInvalideError() from exc
    return cast(TokenPayload, payload)
