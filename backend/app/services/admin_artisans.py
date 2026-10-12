"""Gestion des artisans par l'admin (BUILD_PLAN.md §3.6).

Suspension = décision admin DISTINCTE de la vérification : l'artisan
disparaît de la recherche et devient inéligible aux nouvelles demandes
(`evaluate_engagement`), ses interventions et paiements en cours
continuent. Toute suspension/réactivation exige un motif et est journalisée.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile, ArtisanTrade, Verification
from app.models.enums import (
    ArtisanVerifiedStatus,
    AuditAction,
    AuditTargetType,
    VerificationStatus,
)
from app.models.user import User
from app.schemas.admin import AdminArtisanListItemOut
from app.schemas.pagination import Page
from app.services import audit as audit_service
from app.services.artisans import PageHorsBornesError, get_artisan_or_404
from app.services.text_search import LIKE_ESCAPE, contains_pattern

# Filtre « suspendu » en plus des statuts de vérification.
SUSPENDED_FILTER = "suspended"


class ArtisanDejaSuspenduError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_DEJA_SUSPENDU",
            message="Cet artisan est déjà suspendu.",
            status_code=409,
        )


class ArtisanNonSuspenduError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_NON_SUSPENDU",
            message="Cet artisan n'est pas suspendu.",
            status_code=409,
        )


async def list_artisans(
    session: AsyncSession,
    *,
    status: str | None,
    q: str | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AdminArtisanListItemOut]:
    """Tous les artisans (vérifiés ou non, suspendus compris), filtrables par
    statut de vérification ou « suspended », et par nom / téléphone."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)

    conditions: list[ColumnElement[bool]] = [ArtisanProfile.deleted_at.is_(None)]
    if status == SUSPENDED_FILTER:
        conditions.append(ArtisanProfile.suspended_at.is_not(None))
    elif status is not None:
        conditions.append(ArtisanProfile.verified_status == ArtisanVerifiedStatus(status))
    if q and q.strip():
        pattern = contains_pattern(q.strip())
        conditions.append(
            exists(
                select(User.id).where(
                    User.id == ArtisanProfile.user_id,
                    or_(
                        User.full_name.ilike(pattern, escape=LIKE_ESCAPE),
                        User.phone.ilike(pattern, escape=LIKE_ESCAPE),
                    ),
                )
            )
        )

    pending_documents = (
        select(func.count(Verification.id))
        .where(
            Verification.artisan_id == ArtisanProfile.id,
            Verification.status == VerificationStatus.PENDING,
        )
        .correlate(ArtisanProfile)
        .scalar_subquery()
    )
    stmt = (
        select(ArtisanProfile, pending_documents)
        .where(*conditions)
        .options(
            selectinload(ArtisanProfile.user),
            selectinload(ArtisanProfile.artisan_trades).selectinload(ArtisanTrade.trade),
        )
        .order_by(ArtisanProfile.created_at.desc(), ArtisanProfile.id)
        .limit(resolved)
        .offset((page - 1) * resolved)
    )
    rows = (await session.execute(stmt)).all()
    total = (
        await session.execute(select(func.count()).select_from(ArtisanProfile).where(*conditions))
    ).scalar_one()
    items = [
        AdminArtisanListItemOut(
            id=profile.id,
            full_name=profile.user.full_name,
            phone=profile.user.phone,
            verified_status=profile.verified_status,
            is_suspended=profile.suspended_at is not None,
            trade_labels=sorted(t.trade.label_fr for t in profile.artisan_trades),
            rating_avg=float(profile.rating_avg) if profile.rating_avg is not None else None,
            review_count=profile.review_count,
            pending_documents=int(pending or 0),
            created_at=profile.created_at,
        )
        for profile, pending in rows
    ]
    return Page.of(items, page=page, page_size=resolved, total=total)


async def suspend_artisan(
    session: AsyncSession, *, admin: User, artisan_id: uuid.UUID, reason: str
) -> ArtisanProfile:
    profile = await _lock(session, artisan_id)
    if profile.suspended_at is not None:
        raise ArtisanDejaSuspenduError()
    profile.suspended_at = datetime.now(UTC)
    profile.suspension_reason = reason
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.ARTISAN_SUSPEND,
        target_type=AuditTargetType.ARTISAN,
        target_id=profile.id,
        details={"reason": reason},
    )
    return profile


async def reactivate_artisan(
    session: AsyncSession, *, admin: User, artisan_id: uuid.UUID, note: str | None
) -> ArtisanProfile:
    profile = await _lock(session, artisan_id)
    if profile.suspended_at is None:
        raise ArtisanNonSuspenduError()
    details = {
        "note": note,
        "suspended_at": profile.suspended_at,
        "suspension_reason": profile.suspension_reason,
    }
    profile.suspended_at = None
    profile.suspension_reason = None
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.ARTISAN_REACTIVATE,
        target_type=AuditTargetType.ARTISAN,
        target_id=profile.id,
        details=details,
    )
    return profile


async def _lock(session: AsyncSession, artisan_id: uuid.UUID) -> ArtisanProfile:
    """L'artisan (404 sinon), ligne verrouillée : deux admins ne décident
    jamais en même temps sur le même compte."""
    await get_artisan_or_404(session, artisan_id)
    stmt = (
        select(ArtisanProfile)
        .where(ArtisanProfile.id == artisan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()
