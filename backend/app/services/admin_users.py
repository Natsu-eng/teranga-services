"""Gestion du rôle admin depuis le back-office (BUILD_PLAN.md §3.6, §4.4).

**Décisions de sécurité actées :**

- Le PREMIER admin naît uniquement du script CLI (`scripts/create_admin.py`) ;
  ensuite, un admin promeut ou révoque d'autres comptes ici.
- **Anti-verrouillage** (non négociable) : impossible de retirer son PROPRE
  rôle admin, impossible de retirer le DERNIER admin. Les lignes de tous les
  admins actifs sont verrouillées avant de compter : deux révocations
  simultanées ne peuvent pas vider le back-office.
- Seul l'octroi/retrait du rôle admin se gère ici, jamais client ↔ artisan.
- **Comptes admin dédiés** : un compte n'a qu'un rôle ; promouvoir un
  artisan le priverait de son espace Pro tout en laissant sa fiche publique.
  Seul un compte client sans profil artisan peut être promu. Au retrait,
  le rôle d'origine est DÉDUIT des données (profil artisan existant ->
  artisan, sinon client), jamais deviné.
- Effet immédiat : le rôle est relu en base à chaque requête.
- Chaque octroi et retrait est journalisé (audit_log).
"""

import uuid

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile
from app.models.enums import AuditAction, AuditTargetType, Role
from app.models.user import User
from app.schemas.admin import AdminUserOut
from app.schemas.pagination import Page
from app.services import audit as audit_service
from app.services.artisans import PageHorsBornesError
from app.services.text_search import LIKE_ESCAPE, contains_pattern


class CompteIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(code="USER_NOT_FOUND", message="Compte introuvable.", status_code=404)


class DejaAdminError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEJA_ADMIN", message="Ce compte est déjà administrateur.", status_code=409
        )


class CompteArtisanNonPromouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COMPTE_ARTISAN_NON_PROMOUVABLE",
            message=(
                "Un compte artisan ne peut pas devenir administrateur : un admin utilise "
                "un compte dédié."
            ),
            status_code=409,
        )


class PasAdminError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAS_ADMIN", message="Ce compte n'est pas administrateur.", status_code=409
        )


class RevocationDeSoiError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="REVOCATION_DE_SOI_INTERDITE",
            message=(
                "Vous ne pouvez pas retirer votre propre rôle d'administrateur : "
                "demandez-le à un autre admin."
            ),
            status_code=409,
        )


class DernierAdminError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DERNIER_ADMIN",
            message=(
                "Impossible de retirer le dernier administrateur : promouvez d'abord "
                "un autre compte."
            ),
            status_code=409,
        )


def _has_artisan_profile(user_id_column: object) -> ColumnElement[bool]:
    return exists(
        select(ArtisanProfile.id).where(
            ArtisanProfile.user_id == user_id_column, ArtisanProfile.deleted_at.is_(None)
        )
    )


async def _active_admin_count(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.role == Role.ADMIN, User.deleted_at.is_(None))
    )
    return (await session.execute(stmt)).scalar_one()


async def list_users(
    session: AsyncSession,
    *,
    viewer: User,
    q: str | None,
    role: Role | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AdminUserOut]:
    """Comptes actifs, recherche nom/téléphone, filtre par rôle. Chaque ligne
    dit si l'octroi ou le retrait est possible, et pourquoi pas sinon : les
    garde-fous sont visibles AVANT l'action."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)

    conditions: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
    if role is not None:
        conditions.append(User.role == role)
    if q and q.strip():
        pattern = contains_pattern(q.strip())
        conditions.append(
            or_(
                User.full_name.ilike(pattern, escape=LIKE_ESCAPE),
                User.phone.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    rows = (
        await session.execute(
            _rows_query()
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id)
            .limit(resolved)
            .offset((page - 1) * resolved)
        )
    ).all()
    total = (
        await session.execute(select(func.count()).select_from(User).where(*conditions))
    ).scalar_one()
    admin_count = await _active_admin_count(session)
    items = [
        _to_out(user, has_profile=bool(has_profile), viewer=viewer, admin_count=admin_count)
        for user, has_profile in rows
    ]
    return Page.of(items, page=page, page_size=resolved, total=total)


async def get_user(session: AsyncSession, *, viewer: User, user_id: uuid.UUID) -> AdminUserOut:
    """Une ligne de la liste, relue après une action (mêmes garde-fous)."""
    row = (
        await session.execute(_rows_query().where(User.id == user_id, User.deleted_at.is_(None)))
    ).one_or_none()
    if row is None:
        raise CompteIntrouvableError()
    user, has_profile = row
    admin_count = await _active_admin_count(session)
    return _to_out(user, has_profile=bool(has_profile), viewer=viewer, admin_count=admin_count)


def _rows_query() -> Select[tuple[User, bool]]:
    return select(User, _has_artisan_profile(User.id).label("has_artisan_profile"))


def _to_out(user: User, *, has_profile: bool, viewer: User, admin_count: int) -> AdminUserOut:
    """Calcule ce que l'admin peut faire de ce compte, et sinon POURQUOI
    (`guard`). Les mêmes règles sont revérifiées sous verrou à l'action :
    cette ligne n'est qu'un affichage, jamais une autorisation."""
    is_self = user.id == viewer.id
    guard: str | None = None
    if user.role is Role.ADMIN:
        if is_self:
            guard = "Vous ne pouvez pas retirer votre propre rôle."
        elif admin_count <= 1:
            guard = "Dernier administrateur : il ne peut pas être retiré."
    elif user.role is Role.ARTISAN or has_profile:
        guard = "Compte artisan : un admin utilise un compte dédié."
    return AdminUserOut(
        id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role,
        created_at=user.created_at,
        has_artisan_profile=has_profile,
        is_self=is_self,
        can_grant_admin=user.role is Role.CLIENT and not has_profile,
        can_revoke_admin=user.role is Role.ADMIN and guard is None,
        guard=guard,
    )


async def _lock_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    stmt = (
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise CompteIntrouvableError()
    return user


async def grant_admin(
    session: AsyncSession, *, admin: User, user_id: uuid.UUID, note: str | None
) -> User:
    target = await _lock_user(session, user_id)
    if target.role is Role.ADMIN:
        raise DejaAdminError()
    has_profile = (await session.execute(select(_has_artisan_profile(target.id)))).scalar_one()
    if target.role is not Role.CLIENT or has_profile:
        raise CompteArtisanNonPromouvableError()

    target.role = Role.ADMIN
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.USER_GRANT_ADMIN,
        target_type=AuditTargetType.USER,
        target_id=target.id,
        details={"previous_role": Role.CLIENT, "note": note},
    )
    return target


async def revoke_admin(
    session: AsyncSession, *, admin: User, user_id: uuid.UUID, note: str | None
) -> User:
    # Anti-verrouillage n°1 : jamais son propre rôle.
    if user_id == admin.id:
        raise RevocationDeSoiError()
    # Anti-verrouillage n°2 : jamais le dernier admin. Toutes les lignes admin
    # sont verrouillées (ordre stable : pas d'interblocage) avant de compter ;
    # une révocation concurrente attend, puis recompte sans la ligne retirée.
    admin_ids = list(
        (
            await session.execute(
                select(User.id)
                .where(User.role == Role.ADMIN, User.deleted_at.is_(None))
                .order_by(User.id)
                .with_for_update()
            )
        ).scalars()
    )
    target = await _lock_user(session, user_id)
    if target.id not in admin_ids:
        raise PasAdminError()
    if len(admin_ids) <= 1:
        raise DernierAdminError()

    has_profile = (await session.execute(select(_has_artisan_profile(target.id)))).scalar_one()
    restored = Role.ARTISAN if has_profile else Role.CLIENT
    target.role = restored
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.USER_REVOKE_ADMIN,
        target_type=AuditTargetType.USER,
        target_id=target.id,
        details={"restored_role": restored, "note": note},
    )
    return target
