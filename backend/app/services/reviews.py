"""Garantie applicative de la règle métier « avis conditionné » + dénormalisation.

Un avis (`review`) ne peut exister que si l'intervention liée est
`terminee` (BUILD_PLAN.md §2.2) — c'est la digue anti-faux-avis inspirée de
Checkatrade. Cette garantie est doublée d'un trigger PostgreSQL
(`review_requires_completed_intervention`, posé en migration) qui rejette
l'écriture même si cette fonction est contournée (script, admin SQL direct).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanProfile
from app.models.enums import InterventionStatus, ReviewStatus
from app.models.intervention import Intervention
from app.models.review import Review


class InterventionNotCompletedError(ValueError):
    """Levée quand on tente de créer un avis sur une intervention non terminée."""


def ensure_intervention_completed(intervention: Intervention) -> None:
    if intervention.status is not InterventionStatus.TERMINEE:
        raise InterventionNotCompletedError(
            "Un avis ne peut être laissé que sur une intervention terminée "
            f"(statut actuel : {intervention.status.value})."
        )


async def recalculate_artisan_rating(session: AsyncSession, artisan_id: uuid.UUID) -> None:
    """Recalcule `rating_avg`/`review_count` depuis les avis publiés (BUILD_PLAN.md §6, Lot 9).

    Seuls les avis `status=publie` comptent -- un avis masqué ou signalé
    n'entre plus dans la moyenne. Aucune fonction de création/masquage d'avis
    n'existe encore (Lot 12) : cette fonction est prête à être appelée par ce
    futur lot après toute mutation du statut d'un avis. Idempotente, ne lève
    jamais si `artisan_id` n'existe pas (no-op).
    """
    avg_rating, count = (
        await session.execute(
            select(func.round(func.avg(Review.rating), 2), func.count(Review.id)).where(
                Review.artisan_id == artisan_id, Review.status == ReviewStatus.PUBLIE
            )
        )
    ).one()

    profile = await session.get(ArtisanProfile, artisan_id)
    if profile is None:
        return
    profile.rating_avg = avg_rating
    profile.review_count = count
