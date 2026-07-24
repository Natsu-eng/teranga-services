"""Accès données pour la lecture publique des avis d'un artisan."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.enums import ReviewStatus
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
