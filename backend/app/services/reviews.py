"""Garantie applicative de la règle métier « avis conditionné » + dénormalisation.

Un avis (`review`) ne peut exister que si l'intervention liée est
`terminee` (BUILD_PLAN.md §2.2) — c'est la digue anti-faux-avis inspirée de
Checkatrade. Cette garantie est doublée d'un trigger PostgreSQL
(`review_requires_completed_intervention`, posé en migration) qui rejette
l'écriture même si cette fonction est contournée (script, admin SQL direct).

Signalement (BUILD_PLAN.md §3.6) : l'artisan concerné peut signaler un avis
reçu, une fois, avec un motif. L'avis reste visible et compté jusqu'à la
décision d'un admin (`app.services.admin_reviews`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile
from app.models.enums import InterventionStatus, ReviewStatus
from app.models.intervention import Intervention
from app.models.review import Review
from app.models.user import User
from app.repositories import reviews as reviews_repository
from app.schemas.pagination import Page
from app.schemas.reviews import ArtisanOwnReviewOut, ReviewCreateIn, ReviewOut
from app.services import interventions as interventions_service
from app.services.artisan_errors import PageHorsBornesError
from app.services.artisan_profile import get_own_profile
from app.services.artisans import get_artisan_or_404
from app.services.identity import public_display_name


class InterventionNotCompletedError(ValueError):
    """Levée quand on tente de créer un avis sur une intervention non terminée."""


def ensure_intervention_completed(intervention: Intervention) -> None:
    if intervention.status is not InterventionStatus.TERMINEE:
        raise InterventionNotCompletedError(
            "Un avis ne peut être laissé que sur une intervention terminée "
            f"(statut actuel : {intervention.status.value})."
        )


class AvisInterventionNonTermineeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_INTERVENTION_NON_TERMINEE",
            message="Un avis ne peut être laissé que sur une intervention terminée.",
            status_code=409,
        )


class AvisDejaDeposeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_DEJA_DEPOSE",
            message="Un avis a déjà été déposé pour cette intervention.",
            status_code=409,
        )


class AvisIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(code="REVIEW_NOT_FOUND", message="Avis introuvable.", status_code=404)


class AvisDejaSignaleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_DEJA_SIGNALE",
            message="Cet avis a déjà été signalé : un avis ne peut être signalé qu'une fois.",
            status_code=409,
        )


class AvisMasqueNonSignalableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVIS_DEJA_MASQUE",
            message="Cet avis est déjà masqué par la modération.",
            status_code=409,
        )


async def recalculate_artisan_rating(session: AsyncSession, artisan_id: uuid.UUID) -> None:
    """Recalcule `rating_avg`/`review_count` depuis les avis visibles (BUILD_PLAN.md §6, §3.6).

    Comptent les avis publiés ET signalés en attente de décision ; un avis
    masqué par un admin, ou dont l'intervention est en litige, n'entre plus
    dans la moyenne (`publicly_visible`). À appeler après toute création
    d'avis, changement de statut, ouverture ou décision de litige.

    Le profil est verrouillé AVANT l'agrégat : deux modérations simultanées
    sur des avis du même artisan sont sérialisées, et la seconde, qui relit
    après la validation de la première (READ COMMITTED), calcule sur l'état
    final -- jamais une note périmée. Idempotente, no-op si l'artisan
    n'existe pas.
    """
    profile = (
        await session.execute(
            select(ArtisanProfile)
            .where(ArtisanProfile.id == artisan_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if profile is None:
        return
    avg_rating, count = (
        await session.execute(
            select(func.round(func.avg(Review.rating), 2), func.count(Review.id)).where(
                Review.artisan_id == artisan_id,
                reviews_repository.publicly_visible(),
            )
        )
    ).one()
    profile.rating_avg = avg_rating
    profile.review_count = count


async def list_artisan_reviews(
    session: AsyncSession, artisan_id: uuid.UUID, *, page: int, page_size: int, settings: Settings
) -> Page[ReviewOut]:
    """Avis visibles (publiés, ou signalés en attente de décision) d'un
    artisan, paginés. 404 normalisé (réutilise `get_artisan_or_404`) si
    l'artisan n'existe pas ou est soft-deleted -- même garde que pour le
    profil et les stats.
    """
    await get_artisan_or_404(session, artisan_id)

    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    reviews = await reviews_repository.list_visible_reviews(
        session, artisan_id, limit=resolved_page_size, offset=offset
    )
    total = await reviews_repository.count_visible_reviews(session, artisan_id)

    items = [
        ReviewOut(
            id=review.id,
            rating=review.rating,
            comment=review.comment,
            author_name=public_display_name(review.author.full_name),
            created_at=review.created_at,
            status=review.status,
        )
        for review in reviews
    ]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)


async def create_review(
    session: AsyncSession, *, intervention_id: uuid.UUID, client_user: User, payload: ReviewCreateIn
) -> ReviewOut:
    """Dépose un avis (BUILD_PLAN.md §6 Lot 12b). Autorisé uniquement au
    client propriétaire de l'intervention, uniquement si elle est `terminee`
    (revalidé ici -- une erreur normalisée claire, jamais l'erreur DB brute
    du trigger `review_requires_completed_intervention`, qui reste le filet
    de sécurité final), et une seule fois par intervention. Recalcule
    `rating_avg`/`review_count` de l'artisan à la volée.
    """
    intervention = await interventions_service.get_intervention_or_404(session, intervention_id)
    interventions_service.ensure_is_client(intervention, client_user)

    if intervention.review is not None:
        raise AvisDejaDeposeError()

    try:
        ensure_intervention_completed(intervention)
    except InterventionNotCompletedError as exc:
        raise AvisInterventionNonTermineeError() from exc

    review = await reviews_repository.create_review(
        session,
        intervention=intervention,
        author_id=client_user.id,
        artisan_id=intervention.artisan_id,
        rating=payload.rating,
        comment=payload.comment,
        contact_verified=client_user.phone_verified_at is not None,
    )
    await recalculate_artisan_rating(session, intervention.artisan_id)

    return ReviewOut(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        author_name=public_display_name(client_user.full_name),
        created_at=review.created_at,
        status=review.status,
    )


def to_own_review(review: Review) -> ArtisanOwnReviewOut:
    return ArtisanOwnReviewOut(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        author_name=public_display_name(review.author.full_name),
        created_at=review.created_at,
        status=review.status,
        report_reason=review.report_reason,
        reported_at=review.reported_at,
        # Un seul signalement par avis, et seulement sur un avis publié.
        can_report=review.reported_at is None and review.status is ReviewStatus.PUBLIE,
    )


async def list_own_reviews(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[ArtisanOwnReviewOut]:
    """Tous les avis reçus par l'artisan courant, MASQUÉS compris : il voit
    ce que la modération a décidé à son sujet (transparence)."""
    profile = await get_own_profile(session, user)
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)
    stmt = (
        select(Review)
        .where(Review.artisan_id == profile.id)
        .options(joinedload(Review.author))
        .order_by(Review.created_at.desc(), Review.id)
        .limit(resolved)
        .offset((page - 1) * resolved)
    )
    reviews = list((await session.execute(stmt)).unique().scalars())
    total = (
        await session.execute(
            select(func.count()).select_from(Review).where(Review.artisan_id == profile.id)
        )
    ).scalar_one()
    items = [to_own_review(review) for review in reviews]
    return Page.of(items, page=page, page_size=resolved, total=total)


async def report_review(
    session: AsyncSession, *, user: User, review_id: uuid.UUID, reason: str
) -> ArtisanOwnReviewOut:
    """L'artisan concerné signale un avis (une seule fois, motif obligatoire).

    L'avis passe `signale` mais RESTE visible et compté dans la note : un
    admin tranche ensuite (masquer ou maintenir). L'avis d'un autre artisan
    répond 404, comme un id inconnu : on ne révèle rien.
    """
    profile = await get_own_profile(session, user)
    review = (
        await session.execute(
            select(Review)
            .where(Review.id == review_id, Review.artisan_id == profile.id)
            .options(joinedload(Review.author))
            .with_for_update(of=Review)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if review is None:
        raise AvisIntrouvableError()
    if review.status is ReviewStatus.MASQUE:
        raise AvisMasqueNonSignalableError()
    if review.reported_at is not None:
        raise AvisDejaSignaleError()

    review.status = ReviewStatus.SIGNALE
    review.report_reason = reason
    review.reported_at = datetime.now(UTC)
    await session.flush()
    return to_own_review(review)
