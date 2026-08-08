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
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.full_name import validate_full_name
from app.core.security import (
    TokenInvalideError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from app.models.artisan import ArtisanProfile
from app.models.enums import Locale, Role
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.schemas.auth import UserOut

# Seules valeurs acceptables au rôle choisi à l'inscription (BUILD_PLAN.md
# §4) : `admin` n'est **jamais** attribuable via l'application, aucun
# endpoint, aucun paramètre. Allow-list explicite plutôt que de compter
# uniquement sur le typage `Literal` du schéma -- ce test-ci est le
# chokepoint greppable et testé de cet invariant de sécurité.
_SIGNUP_ROLES = {Role.CLIENT, Role.ARTISAN}


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


class RoleInscriptionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ROLE_INSCRIPTION_INVALIDE",
            message="Rôle invalide. Choisissez « client » ou « artisan ».",
            status_code=422,
        )


class CompteDejaExistantError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COMPTE_DEJA_EXISTANT",
            message="Un compte existe déjà avec ce numéro. Connectez-vous.",
            status_code=409,
        )


class CompteInexistantError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COMPTE_INEXISTANT",
            message="Aucun compte pour ce numéro. Inscrivez-vous.",
            status_code=404,
        )


async def resolve_account_for_intent(
    session: AsyncSession,
    phone: str,
    *,
    intent: Literal["login", "signup"],
    role: Literal["client", "artisan"] | None,
    full_name: str | None = None,
) -> User:
    """Traduit `(phone, intent, role)` en `User`, après vérification OTP réussie
    (BUILD_PLAN.md §4). En signup, crée le compte (et son `artisan_profile`
    vide si `role == artisan`) -- jamais si le numéro existe déjà. En login,
    retrouve le compte existant -- n'en crée jamais. Un compte existant ne
    change jamais de rôle (ni de nom) via ce flux (le login ne le touche
    pas, le signup rejette purement et simplement un numéro déjà pris).
    """
    now = datetime.now(UTC)
    existing = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()

    if intent == "signup":
        if role not in ("client", "artisan"):
            raise RoleInscriptionInvalideError()
        if existing is not None:
            raise CompteDejaExistantError()

        # Le nom est requis pour les deux rôles (fix confidentialité du
        # contact, BUILD_PLAN.md) : plus jamais de placeholder = le
        # téléphone. `validate_full_name` rejette aussi bien `None` (via le
        # `or ""`) qu'une chaîne vide/trop courte après trim -- un seul
        # message actionnable, "le nom est requis".
        validated_full_name = validate_full_name(full_name or "")

        signup_role = Role.ARTISAN if role == "artisan" else Role.CLIENT
        assert signup_role in _SIGNUP_ROLES  # invariant : jamais Role.ADMIN ici
        user = User(
            phone=phone,
            full_name=validated_full_name,
            role=signup_role,
            locale=Locale.FR,
            phone_verified_at=now,
        )
        session.add(user)
        await session.flush()

        if signup_role == Role.ARTISAN:
            session.add(
                ArtisanProfile(
                    user_id=user.id,
                    # Vide/minimal : aucun document soumis, aucune zone
                    # définie -- l'onboarding (bio, métiers, zone, documents
                    # de vérification) est un chantier distinct (Lot B).
                    # `is_available=False` explicite : contrairement au
                    # défaut du modèle (`True`, utilisé par le seed et les
                    # tests), un artisan fraîchement inscrit ne doit pas
                    # apparaître disponible avant d'avoir complété son profil.
                    is_available=False,
                )
            )
            await session.flush()
        return user

    # intent == "login"
    if existing is None:
        raise CompteInexistantError()
    if existing.phone_verified_at is None:
        existing.phone_verified_at = now
    return existing


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
