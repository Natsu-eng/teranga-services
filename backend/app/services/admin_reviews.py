"""Modération des avis par l'admin (BUILD_PLAN.md §3.6).

- Un avis n'est JAMAIS supprimé : l'admin le masque (motif obligatoire) ou
  le maintient/rétablit ; les deux sont réversibles et journalisés.
- Masquer : `publie` ou `signale` -> `masque`. Rétablir : `masque` ou
  `signale` -> `publie` (pour un avis signalé : « signalement examiné, avis
  maintenu »). Le signalement d'origine reste en historique sur l'avis.
- La note de l'artisan est recalculée à chaque décision (profil verrouillé
  dans `recalculate_artisan_rating` : modérations concurrentes sérialisées).
- L'admin voit l'auteur réel (nom complet) : il en a besoin pour juger ; le
  public, lui, ne voit jamais que le nom abrégé.
"""

import uuid

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.base import ExecutableOption

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile
from app.models.enums import AuditAction, AuditTargetType, ReviewStatus
from app.models.review import Review
from app.models.user import User
from app.schemas.admin import AdminReviewOut
from app.schemas.pagination import Page
from app.services import audit as audit_service
from app.services.artisans import PageHorsBornesError
from app.services.reviews import AvisIntrouvableError, recalculate_artisan_rating
from app.services.text_search import LIKE_ESCAPE, contains_pattern


class AvisDejaMasqueError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_DEJA_MASQUE", message="Cet avis est déjà masqué.", status_code=409
        )


class AvisDejaPublieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_DEJA_PUBLIE", message="Cet avis est déjà publié.", status_code=409
        )


def _to_out(review: Review) -> AdminReviewOut:
    return AdminReviewOut(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        status=review.status,
        contact_verified=review.contact_verified,
        created_at=review.created_at,
        intervention_id=review.intervention_id,
        author_id=review.author_id,
        author_name=review.author.full_name,
        artisan_id=review.artisan_id,
        artisan_name=review.artisan.user.full_name,
        report_reason=review.report_reason,
        reported_at=review.reported_at,
    )


def _with_people() -> tuple[ExecutableOption, ...]:
    return (
        joinedload(Review.author),
        joinedload(Review.artisan).joinedload(ArtisanProfile.user),
    )


async def list_reviews(
    session: AsyncSession,
    *,
    status: ReviewStatus | None,
    artisan_id: uuid.UUID | None,
    q: str | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AdminReviewOut]:
    """Avis filtrables par statut, artisan et texte (commentaire ou nom de
    l'auteur). Les signalés d'abord quand aucun statut n'est imposé : ce
    sont ceux qui attendent une décision."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)

    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(Review.status == status)
    if artisan_id is not None:
        conditions.append(Review.artisan_id == artisan_id)
    if q and q.strip():
        pattern = contains_pattern(q.strip())
        conditions.append(
            or_(
                Review.comment.ilike(pattern, escape=LIKE_ESCAPE),
                Review.author_id.in_(
                    select(User.id).where(User.full_name.ilike(pattern, escape=LIKE_ESCAPE))
                ),
            )
        )
    pending_first = (Review.status == ReviewStatus.SIGNALE).desc()
    stmt = (
        select(Review)
        .where(*conditions)
        .options(*_with_people())
        .order_by(pending_first, Review.created_at.desc(), Review.id)
        .limit(resolved)
        .offset((page - 1) * resolved)
    )
    reviews = list((await session.execute(stmt)).unique().scalars())
    total = (
        await session.execute(select(func.count()).select_from(Review).where(*conditions))
    ).scalar_one()
    return Page.of(
        [_to_out(review) for review in reviews], page=page, page_size=resolved, total=total
    )


async def _lock(session: AsyncSession, review_id: uuid.UUID) -> Review:
    stmt = (
        select(Review)
        .where(Review.id == review_id)
        .options(*_with_people())
        .with_for_update(of=Review)
        .execution_options(populate_existing=True)
    )
    review = (await session.execute(stmt)).unique().scalar_one_or_none()
    if review is None:
        raise AvisIntrouvableError()
    return review


async def hide_review(
    session: AsyncSession, *, admin: User, review_id: uuid.UUID, reason: str
) -> AdminReviewOut:
    review = await _lock(session, review_id)
    if review.status is ReviewStatus.MASQUE:
        raise AvisDejaMasqueError()
    previous = review.status
    review.status = ReviewStatus.MASQUE
    await session.flush()
    await recalculate_artisan_rating(session, review.artisan_id)
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.REVIEW_HIDE,
        target_type=AuditTargetType.REVIEW,
        target_id=review.id,
        details={
            "reason": reason,
            "previous_status": previous,
            "rating": review.rating,
            "artisan_id": review.artisan_id,
        },
    )
    return _to_out(review)


async def restore_review(
    session: AsyncSession, *, admin: User, review_id: uuid.UUID, note: str | None
) -> AdminReviewOut:
    review = await _lock(session, review_id)
    if review.status is ReviewStatus.PUBLIE:
        raise AvisDejaPublieError()
    previous = review.status
    review.status = ReviewStatus.PUBLIE
    await session.flush()
    await recalculate_artisan_rating(session, review.artisan_id)
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.REVIEW_RESTORE,
        target_type=AuditTargetType.REVIEW,
        target_id=review.id,
        details={
            "note": note,
            "previous_status": previous,
            "rating": review.rating,
            "artisan_id": review.artisan_id,
        },
    )
    return _to_out(review)
