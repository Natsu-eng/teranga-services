"""Litiges sur une intervention (BUILD_PLAN.md §3.5) : ouverture par une
partie, arbitrage par un admin (journalisé), liste pour le back-office.

Extraits de `app.services.interventions` sans changement de logique :
l'argent reste gelé pendant le litige, l'arbitrage règle le volet financier
dans la même transaction, sous verrou de la ligne.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.enums import (
    AuditAction,
    AuditTargetType,
    DisputeOutcome,
    InterventionCancellationKind,
    InterventionStatus,
    Role,
    ServiceRequestStatus,
)
from app.models.intervention import InterventionDispute
from app.models.user import User
from app.repositories import interventions as interventions_repository
from app.repositories import payments as payments_repository
from app.repositories import requests as requests_repository
from app.schemas.interventions import (
    InterventionOut,
)
from app.schemas.pagination import Page
from app.services import audit as audit_service
from app.services import payments as payments_service
from app.services.artisans import PageHorsBornesError
from app.services.intervention_errors import (
    InterventionTransitionInvalideError,
)
from app.services.interventions import (
    SettledIntervention,
    _get_for_update_or_404,
    _party_role,
    mark_cancelled,
    to_intervention_out,
    transition_intervention,
)
from app.services.payment_providers.base import PaymentProvider


async def open_dispute(
    session: AsyncSession, *, intervention_id: uuid.UUID, user: User, reason: str
) -> InterventionOut:
    """Une partie signale un problème sur des travaux en cours
    (`en_cours` -> `litige`). L'argent est GELÉ tel quel -- ni versement ni
    remboursement -- jusqu'à la décision d'un admin. C'est aussi le recours
    de l'artisan quand un client ne confirme jamais la fin des travaux."""
    intervention = await _get_for_update_or_404(session, intervention_id)
    role = _party_role(intervention, user)
    transition_intervention(intervention, InterventionStatus.LITIGE)
    dispute = InterventionDispute(
        intervention=intervention,
        opened_by_id=user.id,
        opened_by_role=role,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    session.add(dispute)
    await session.flush()
    return to_intervention_out(intervention)


async def resolve_dispute(
    session: AsyncSession,
    *,
    intervention_id: uuid.UUID,
    admin: User,
    outcome: DisputeOutcome,
    note: str,
    settings: Settings,
    provider: PaymentProvider | None,
) -> SettledIntervention:
    """Un admin tranche un litige (BUILD_PLAN.md §3.5) :

    - `libere` : travaux reconnus faits -> `terminee`, même enchaînement
      qu'une complétion (séquestre libéré, versement du net) ;
    - `rembourse` : -> `annulee` (arbitrage), client remboursé, ni
      versement ni commission.
    """
    intervention = await _get_for_update_or_404(session, intervention_id)
    dispute = intervention.dispute
    if intervention.status is not InterventionStatus.LITIGE or dispute is None:
        raise InterventionTransitionInvalideError()

    payout = None
    if outcome is DisputeOutcome.LIBERE:
        transition_intervention(intervention, InterventionStatus.TERMINEE)
        intervention.completed_at = datetime.now(UTC)
        payout = payments_service.settle_on_completion(session, intervention, settings=settings)
    else:
        transition_intervention(intervention, InterventionStatus.ANNULEE)
        mark_cancelled(
            intervention, by=Role.ADMIN, kind=InterventionCancellationKind.ARBITRAGE, reason=note
        )
        await payments_service.settle_on_cancellation(
            session, intervention, settings=settings, provider=provider
        )
        await requests_repository.set_status(
            session, intervention.service_request, ServiceRequestStatus.OUVERTE
        )
    dispute.outcome = outcome
    dispute.resolved_by_id = admin.id
    dispute.resolved_at = datetime.now(UTC)
    dispute.resolution_note = note
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.DISPUTE_RESOLVE,
        target_type=AuditTargetType.INTERVENTION,
        target_id=intervention.id,
        details={
            "outcome": outcome,
            "note": note,
            "opened_by": dispute.opened_by_role,
            "payout_id": payout.id if payout is not None else None,
        },
    )
    return SettledIntervention(
        intervention=to_intervention_out(intervention),
        payout_id=payout.id if payout is not None else None,
    )


async def list_disputes(
    session: AsyncSession, *, resolved: bool, page: int, page_size: int, settings: Settings
) -> Page[InterventionOut]:
    """File des litiges pour l'admin : ouverts (premier ouvert, premier
    tranché) ou déjà tranchés."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size
    ids = await payments_repository.list_disputed_intervention_ids(
        session, resolved=resolved, limit=resolved_page_size, offset=offset
    )
    total = await payments_repository.count_disputes(session, resolved=resolved)
    interventions = await interventions_repository.list_by_ids(session, ids)
    items = [to_intervention_out(intervention) for intervention in interventions]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)
