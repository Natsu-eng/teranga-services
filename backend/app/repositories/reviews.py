"""Accès données pour les avis d'un artisan (lecture publique + écriture)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.enums import ReviewStatus
from app.models.intervention import Intervention
from app.models.review import Review


async def list_published_reviews(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int, offset: int
) -> list[Review]:
    stmt = (
        select(Review)
        .where(Review.artisan_id == artisan_id, Review.status == ReviewStatus.PUBLIE)
        .options(joinedload(Review.author))
        .order_by(Review.created_at.desc(), Review.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def count_published_reviews(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Review)
        .where(Review.artisan_id == artisan_id, Review.status == ReviewStatus.PUBLIE)
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
