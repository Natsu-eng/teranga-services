"""Erreurs communes aux opérations sur une intervention (BUILD_PLAN.md §6
Lot 12, §3.5).

Module séparé de `app.services.interventions` pour que les paiements
(`app.services.payments`) puissent les lever sans dépendre du service des
interventions -- qui, lui, s'appuie sur les paiements (complétion,
annulation). `app.services.interventions` les réexporte : les imports
existants restent valides.
"""

from app.core.errors import AppError


class InterventionIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_NOT_FOUND", message="Intervention introuvable.", status_code=404
        )


class InterventionAccesInterditError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette intervention.",
            status_code=403,
        )


class InterventionTransitionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TRANSITION_INTERVENTION_INVALIDE",
            message="Cette action n'est pas possible dans l'état actuel de l'intervention.",
            status_code=409,
        )


class ActionReserveeAutrePartieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ACTION_RESERVEE_AUTRE_PARTIE",
            message="Cette action est réservée à l'autre partie de cette intervention.",
            status_code=403,
        )
