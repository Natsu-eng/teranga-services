"""Accès données pour les avis d'un artisan (lecture publique + écriture)."""

import uuid

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.enums import InterventionStatus, ReviewStatus, Role
from app.models.intervention import Intervention, InterventionDispute
from app.models.review import Review

# Avis visibles et comptés dans la note : publiés, et signalés EN ATTENTE de
# décision (un signalement seul ne fait jamais disparaître une critique ;
# seul un admin peut masquer, de façon journalisée et réversible).
VISIBLE_REVIEW_STATUSES = (ReviewStatus.PUBLIE, ReviewStatus.SIGNALE)


def publicly_visible() -> ColumnElement[bool]:
    """Avis montré au public ET compté dans la note : statut visible, et pas
    suspendu par un litige du CLIENT.

    Le client qui signale un problème après les travaux suspend son propre
    avis le temps de la décision ; il redevient public dès qu'elle est
    rendue, quelle qu'elle soit (statut sorti de `litige`). Un litige ouvert
    par l'ARTISAN ne suspend jamais l'avis : sinon un artisan pourrait faire
    disparaître une critique en ouvrant un litige (anti-censure)."""
    suspended_by_client_dispute = exists().where(
        Intervention.id == Review.intervention_id,
        Intervention.status == InterventionStatus.LITIGE,
        InterventionDispute.intervention_id == Intervention.id,
        InterventionDispute.opened_by_role == Role.CLIENT,
    )
    return and_(Review.status.in_(VISIBLE_REVIEW_STATUSES), ~suspended_by_client_dispute)


async def list_visible_reviews(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int, offset: int
) -> list[Review]:
    stmt = (
        select(Review)
        .where(Review.artisan_id == artisan_id, publicly_visible())
        .options(joinedload(Review.author))
        .order_by(Review.created_at.desc(), Review.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def count_visible_reviews(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Review)
        .where(Review.artisan_id == artisan_id, publicly_visible())
    )
    return (await session.execute(stmt)).scalar_one()


async def create_review(
    session: AsyncSession,
    *,
    intervention: Intervention,
    author_id: uuid.UUID,
    artisan_id: uuid.UUID,
    rating: int,
    comment: str,
    contact_verified: bool,
) -> Review:
    # `intervention=intervention` (pas `intervention_id=`) : peuple
    # `intervention.review` en mémoire immédiatement -- utile si l'appelant
    # sérialise l'intervention juste après (pas de lazy load hors async).
    review = Review(
        intervention=intervention,
        author_id=author_id,
        artisan_id=artisan_id,
        rating=rating,
        comment=comment,
        contact_verified=contact_verified,
        status=ReviewStatus.PUBLIE,
    )
    session.add(review)
    await session.flush()
    return review
