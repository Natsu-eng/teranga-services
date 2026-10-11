"""Dépendances FastAPI d'authentification et d'autorisation (BUILD_PLAN.md §4).

`get_current_user` valide l'access token et charge l'utilisateur ; `require_role`
restreint un endpoint à un sous-ensemble de rôles ; `get_current_user_optional`
sert les endpoints à accès mixte (comportement différent connecté/anonyme,
mais accessibles sans authentification).

**Règle critique (point d'audit « userRole auto-déclarable »)** : aucune
dépendance ni endpoint de ce module ne permet à un utilisateur de modifier
son propre rôle. `role` n'est jamais lu depuis une requête entrante, il est
toujours dérivé de `user.role` en base. Le passage à `artisan` se fera via
la création d'un `artisan_profile` (lot métier, avec vérification de
documents) ; `admin` ne s'attribue que hors application (script/SQL direct).
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import TokenInvalideError, decode_token
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.services.payment_providers import build_payment_provider
from app.services.payment_providers.base import PaymentProvider

_bearer_scheme = HTTPBearer(auto_error=False)


class NonAuthentifieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="NON_AUTHENTIFIE", message="Authentification requise.", status_code=401
        )


class RoleInsuffisantError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ROLE_INSUFFISANT",
            message="Vous n'avez pas les droits nécessaires pour cette action.",
            status_code=403,
        )


async def _load_user_from_access_token(token: str, session: AsyncSession) -> User:
    payload = decode_token(token)
    if payload["type"] != "access":
        raise TokenInvalideError()

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise TokenInvalideError() from exc

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise TokenInvalideError()
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise NonAuthentifieError()
    return await _load_user_from_access_token(credentials.credentials, session)


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    if credentials is None:
        return None
    return await _load_user_from_access_token(credentials.credentials, session)


def require_role(*roles: Role) -> Callable[[User], Awaitable[User]]:
    async def _dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise RoleInsuffisantError()
        return user

    return _dependency


def get_payment_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaymentProvider | None:
    """Fournisseur de paiement actif (BUILD_PLAN.md §3.5), `None` si le
    paiement en ligne est coupé. Surchargeable dans les tests (fournisseur
    en panne, par exemple)."""
    return build_payment_provider(settings)
