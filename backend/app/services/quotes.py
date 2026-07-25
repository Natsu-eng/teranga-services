"""Logique métier du devis (BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b).

Le devis est un objet autonome lié à l'intervention, pas un message de chat
(décision actée) : ce module ne connaît que `intervention`/`quote`, jamais la
messagerie. Toute mutation de `intervention.status` passe par
`app.services.interventions.transition_intervention` -- jamais un assignement
direct ici.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import InterventionStatus, QuoteStatus
from app.models.user import User
from app.repositories import quotes as quotes_repository
from app.schemas.interventions import InterventionOut
from app.schemas.quotes import QuoteCreateIn
from app.services import interventions as interventions_service


class QuoteInterventionNonAccepteeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="QUOTE_INTERVENTION_NON_ACCEPTEE",
            message="Un devis ne peut être proposé que sur une intervention acceptée.",
            status_code=409,
        )


class AucunDevisActifError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AUCUN_DEVIS_ACTIF",
            message="Aucun devis en attente pour cette intervention.",
            status_code=409,
        )


async def create_quote(
    session: AsyncSession, *, intervention_id: uuid.UUID, artisan_user: User, payload: QuoteCreateIn
) -> InterventionOut:
    """Pose (ou remplace) le devis de l'intervention (BUILD_PLAN.md §6 Lot 12b).

    Le total est calculé côté serveur -- jamais reçu du client -- pour
    garantir par construction la contrainte `total_fcfa = labor_fcfa +
    materials_fcfa` (Lot 7). Un seul devis actif : un re-devis (après refus
    du précédent) remplace la ligne existante plutôt que d'en empiler une
    seconde (`app.repositories.quotes.create_or_replace_quote`).
    """
    intervention = await interventions_service.get_intervention_or_404(session, intervention_id)
    interventions_service.ensure_is_artisan(intervention, artisan_user)
    if intervention.status is not InterventionStatus.ACCEPTEE:
        raise QuoteInterventionNonAccepteeError()

    total_fcfa = payload.labor_fcfa + payload.materials_fcfa
    await quotes_repository.create_or_replace_quote(
        session,
        intervention=intervention,
        labor_fcfa=payload.labor_fcfa,
        materials_fcfa=payload.materials_fcfa,
        total_fcfa=total_fcfa,
    )
    return interventions_service.to_intervention_out(intervention)


async def accept_quote(
    session: AsyncSession, *, intervention_id: uuid.UUID, client_user: User
) -> InterventionOut:
    """Le client accepte le devis : `quote` -> `accepte`, `intervention` ->
    `en_cours`, `agreed_amount_fcfa` renseigné depuis le total du devis
    (BUILD_PLAN.md §6 Lot 12b)."""
    intervention = await interventions_service.get_intervention_or_404(session, intervention_id)
    interventions_service.ensure_is_client(intervention, client_user)

    quote = intervention.quote
    if quote is None or quote.status is not QuoteStatus.PROPOSE:
        raise AucunDevisActifError()

    quote.status = QuoteStatus.ACCEPTE
    intervention.agreed_amount_fcfa = quote.total_fcfa
    interventions_service.transition_intervention(intervention, InterventionStatus.EN_COURS)
    await session.flush()
    return interventions_service.to_intervention_out(intervention)


async def refuse_quote(
    session: AsyncSession, *, intervention_id: uuid.UUID, client_user: User
) -> InterventionOut:
    """Le client refuse le devis : `quote` -> `refuse`, l'intervention reste
    `acceptee` -- l'artisan peut re-deviser (BUILD_PLAN.md §6 Lot 12b)."""
    intervention = await interventions_service.get_intervention_or_404(session, intervention_id)
    interventions_service.ensure_is_client(intervention, client_user)

    quote = intervention.quote
    if quote is None or quote.status is not QuoteStatus.PROPOSE:
        raise AucunDevisActifError()

    quote.status = QuoteStatus.REFUSE
    await session.flush()
    return interventions_service.to_intervention_out(intervention)
