"""Garantie applicative de la règle métier « avis conditionné ».

Un avis (`review`) ne peut exister que si l'intervention liée est
`terminee` (BUILD_PLAN.md §2.2) — c'est la digue anti-faux-avis inspirée de
Checkatrade. Cette garantie est doublée d'un trigger PostgreSQL
(`review_requires_completed_intervention`, posé en migration) qui rejette
l'écriture même si cette fonction est contournée (script, admin SQL direct).
"""

from app.models.enums import InterventionStatus
from app.models.intervention import Intervention


class InterventionNotCompletedError(ValueError):
    """Levée quand on tente de créer un avis sur une intervention non terminée."""


def ensure_intervention_completed(intervention: Intervention) -> None:
    if intervention.status is not InterventionStatus.TERMINEE:
        raise InterventionNotCompletedError(
            "Un avis ne peut être laissé que sur une intervention terminée "
            f"(statut actuel : {intervention.status.value})."
        )
