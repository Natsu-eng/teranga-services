"""Émission et vérification des JWT (BUILD_PLAN.md §4.2).

Payload : `sub` (id utilisateur), `role`, `jti`, `iat`, `exp`, `type`
(`"access"`, `"refresh"` ou `"ws"`) -- le claim `type` empêche qu'un jeton
soit accepté là où un autre type est attendu (un refresh token comme access
token, un ticket WebSocket comme access token, etc.).
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

TokenType = Literal["access", "refresh", "ws"]


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


def encode_ws_ticket(user: User, *, settings: Settings | None = None) -> tuple[str, uuid.UUID]:
    """Ticket d'ouverture d'un WebSocket (BUILD_PLAN.md §3.2, Messagerie).

    Délivré par un appel REST authentifié, il ne sert QU'À ouvrir une
    connexion temps réel : type dédié `"ws"` (refusé partout ailleurs), durée
    de vie très courte, et usage unique (son `jti` est consommé à la
    connexion, voir app.services.realtime). Renvoie aussi le `jti`.
    """
    settings = settings or get_settings()
    jti = uuid.uuid4()
    token = _encode(
        user,
        token_type="ws",
        ttl_seconds=settings.ws_ticket_ttl_seconds,
        jti=jti,
        settings=settings,
    )
    return token, jti
