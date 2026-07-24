"""Recalcul dénormalisé rating_avg/review_count (BUILD_PLAN.md §6, Lot 9)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReviewStatus, Role
from app.services.reviews import recalculate_artisan_rating
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_review,
    make_service_request,
    make_trade,
    make_user,
)


async def test_recalculate_with_no_reviews_leaves_rating_null(db_session: AsyncSession) -> None:
    artisan = await make_artisan_profile(db_session)

    await recalculate_artisan_rating(db_session, artisan.id)

    assert artisan.rating_avg is None
    assert artisan.review_count == 0


async def test_recalculate_averages_published_reviews_only(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)

    for rating in (5, 3):
        client = await make_user(db_session, role=Role.CLIENT)
        service_request = await make_service_request(db_session, client=client, trade=trade)
        intervention = await make_intervention(
            db_session,
            service_request=service_request,
            client=client,
            artisan=artisan,
            commission_rate=commission_rate,
        )
        await make_review(
            db_session, intervention=intervention, author=client, artisan=artisan, rating=rating
        )

    await recalculate_artisan_rating(db_session, artisan.id)

    assert artisan.rating_avg == Decimal("4.00")
    assert artisan.review_count == 2


async def test_recalculate_excludes_hidden_reviews(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    artisan = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)

    ratings_and_status = [(5, ReviewStatus.PUBLIE), (1, ReviewStatus.PUBLIE)]
    reviews = []
    for rating, status in ratings_and_status:
        client = await make_user(db_session, role=Role.CLIENT)
        service_request = await make_service_request(db_session, client=client, trade=trade)
        intervention = await make_intervention(
            db_session,
            service_request=service_request,
            client=client,
            artisan=artisan,
            commission_rate=commission_rate,
        )
        review = await make_review(
            db_session,
            intervention=intervention,
            author=client,
            artisan=artisan,
            rating=rating,
            status=status,
        )
        reviews.append(review)

    await recalculate_artisan_rating(db_session, artisan.id)
    assert artisan.rating_avg == Decimal("3.00")
    assert artisan.review_count == 2

    # On masque l'avis à 1 étoile : la moyenne doit remonter à 5.00 sur le
    # seul avis publié restant, après un nouveau recalcul explicite --
    # jamais automatique, c'est bien la fonction qu'il faut rappeler.
    reviews[1].status = ReviewStatus.MASQUE
    await db_session.flush()

    await recalculate_artisan_rating(db_session, artisan.id)
    assert artisan.rating_avg == Decimal("5.00")
    assert artisan.review_count == 1
