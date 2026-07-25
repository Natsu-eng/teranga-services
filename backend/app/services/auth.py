"""Émission, rotation et révocation des sessions JWT (BUILD_PLAN.md §4.2).

Le refresh token est persisté (table `refresh_token`, haché -- jamais en
clair) : chaque `/refresh` révoque l'ancien et en émet un nouveau
(rotation). Si un refresh **déjà révoqué** est présenté, c'est le signal
d'un vol (rejeu après que le titulaire légitime a déjà tourné) : toute la
famille de refresh tokens de l'utilisateur est révoquée, forçant une
reconnexion complète sur tous les appareils.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import (
    TokenInvalideError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.schemas.auth import UserOut


class RefreshInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="REFRESH_INVALIDE",
            message="Session invalide, merci de vous reconnecter.",
            status_code=401,
        )


class RefreshReutiliseError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="REFRESH_REUTILISE",
            message=(
                "Session compromise détectée, merci de vous reconnecter sur tous vos appareils."
            ),
            status_code=401,
        )


async def to_user_out(session: AsyncSession, user: User) -> UserOut:
    """Assemble `UserOut` en fermant le lien `user <-> artisan_profile`
    (AUDIT_PHASE2.md §6) : `artisan_profile_id` est résolu depuis la base,
    jamais lu depuis une relation ORM potentiellement non chargée. `None`
    pour un client, ou un artisan sans profil créé.
    """
    artisan_profile_id = await artisans_repository.get_artisan_profile_id_by_user_id(
        session, user.id
    )
    return UserOut(
        id=user.id,
        phone=user.phone,
        full_name=user.full_name,
        role=user.role,
        locale=user.locale,
        phone_verified_at=user.phone_verified_at,
        created_at=user.created_at,
        artisan_profile_id=artisan_profile_id,
    )


def _hash_token(token: str) -> str:
    # Pas de sel : le token porte déjà >= 128 bits d'entropie (jti aléatoire
    # + signature HMAC), contrairement au code OTP -- un hachage rapide non
    # salé suffit ici, il ne sert qu'à ne jamais stocker le token en clair.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_token_pair(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, str]:
    """Émet un nouveau couple access/refresh et persiste la session refresh."""
    settings = settings or get_settings()
    jti = uuid.uuid4()
    refresh = encode_refresh_token(user, jti=jti, settings=settings)
    access = encode_access_token(user, settings=settings)

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh),
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
            user_agent=user_agent,
            ip=ip,
        )
    )
    await session.flush()
    return access, refresh


async def _find_stored_token(session: AsyncSession, jti_raw: str) -> RefreshToken | None:
    try:
        jti = uuid.UUID(jti_raw)
    except ValueError:
        return None
    result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    return result.scalar_one_or_none()


async def _revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    for token in result.scalars():
        token.revoked_at = now
    await session.flush()


async def rotate_refresh_token(
    session: AsyncSession,
    refresh_token: str,
    *,
    settings: Settings | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, str]:
    """Vérifie `refresh_token`, le révoque, et émet un nouveau couple (rotation).

    Si le token présenté est déjà révoqué, révoque toute la famille de
    l'utilisateur (signal de vol) et rejette la requête.
    """
    settings = settings or get_settings()
    payload = decode_token(refresh_token, settings=settings)
    if payload["type"] != "refresh":
        raise RefreshInvalideError()

    stored = await _find_stored_token(session, payload["jti"])
    if stored is None:
        raise RefreshInvalideError()
    if not secrets.compare_digest(_hash_token(refresh_token), stored.token_hash):
        raise RefreshInvalideError()

    if stored.revoked_at is not None:
        await _revoke_all_for_user(session, stored.user_id)
        raise RefreshReutiliseError()

    stored.revoked_at = datetime.now(UTC)

    user = await session.get(User, stored.user_id)
    if user is None:
        raise RefreshInvalideError()

    return await issue_token_pair(session, user, settings=settings, user_agent=user_agent, ip=ip)


async def revoke_refresh_token(
    session: AsyncSession, refresh_token: str, *, settings: Settings | None = None
) -> None:
    """Révoque `refresh_token` (logout). Ne lève jamais : un logout avec un
    token déjà invalide/inconnu doit rester silencieux (idempotent, pas
    d'oracle sur la validité du token).
    """
    settings = settings or get_settings()
    try:
        payload = decode_token(refresh_token, settings=settings)
    except TokenInvalideError:
        return
    if payload["type"] != "refresh":
        return

    stored = await _find_stored_token(session, payload["jti"])
    if stored is None:
        return
    if not secrets.compare_digest(_hash_token(refresh_token), stored.token_hash):
        return

    stored.revoked_at = datetime.now(UTC)
    await session.flush()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Révoque toutes les sessions actives de l'utilisateur (logout-all)."""
    await _revoke_all_for_user(session, user_id)
