"""Litiges sur une intervention (BUILD_PLAN.md §3.5) : ouverture par une
partie, arbitrage par un admin (journalisé), liste pour le back-office.

- **Ouverture** : pendant les travaux, ou après leur fin pendant
  DISPUTE_WINDOW_HOURS (règles pures : `app.services.dispute_rules`). Un seul
  litige par intervention. Motif MASQUÉ à l'écriture (numéros, e-mails),
  comme la messagerie : il est montré à l'autre partie.
- **Pendant le litige** : l'argent RETENU en ligne reste gelé ; l'avis
  éventuel n'est plus public (note de l'artisan recalculée).
- **Arbitrage** (sous verrou de la ligne, même transaction que le volet
  financier) : les valeurs stockées restent `libere`/`rembourse`, mais
  l'effet dépend de l'argent réellement détenu -- jamais de « remboursement »
  que Téranga ne peut pas faire (espèces, règlement hors plateforme).
"""

import uuid
from dataclasses import dataclass
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
from app.services import reviews as reviews_service
from app.services.artisan_errors import PageHorsBornesError
from app.services.contact_masking import mask_contacts
from app.services.dispute_rules import DisputeRefusal, dispute_refusal
from app.services.intervention_errors import (
    InterventionTransitionInvalideError,
    LitigeDejaOuvertError,
    LitigeDelaiDepasseError,
    LitigePaiementDejaVerseError,
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

_REFUSAL_ERRORS = {
    DisputeRefusal.TRANSITION: InterventionTransitionInvalideError,
    DisputeRefusal.ALREADY_DISPUTED: LitigeDejaOuvertError,
    DisputeRefusal.WINDOW_ELAPSED: LitigeDelaiDepasseError,
    DisputeRefusal.ONLINE_PAYMENT_RELEASED: LitigePaiementDejaVerseError,
}


@dataclass(frozen=True)
class OpenedDispute:
    """Litige ouvert, et ce qu'il faut pour prévenir les admins (APRÈS le
    commit) : le métier et qui a signalé -- jamais le motif."""

    intervention: InterventionOut
    trade_label: str
    opened_by: Role


async def open_dispute(
    session: AsyncSession,
    *,
    intervention_id: uuid.UUID,
    user: User,
    reason: str,
    settings: Settings,
) -> OpenedDispute:
    """Une partie signale un problème (`en_cours` ou `terminee` -> `litige`).
    L'argent retenu en ligne est GELÉ tel quel -- ni versement ni
    remboursement -- jusqu'à la décision d'un admin. C'est aussi le recours
    de l'artisan quand un client ne confirme jamais la fin des travaux."""
    intervention = await _get_for_update_or_404(session, intervention_id)
    role = _party_role(intervention, user)
    refusal = dispute_refusal(
        intervention, window_hours=settings.dispute_window_hours, now=datetime.now(UTC)
    )
    if refusal is not None:
        raise _REFUSAL_ERRORS[refusal]()
    had_review = intervention.review is not None
    transition_intervention(intervention, InterventionStatus.LITIGE)
    dispute = InterventionDispute(
        intervention=intervention,
        opened_by_id=user.id,
        opened_by_role=role,
        # Montré à l'autre partie : jamais un numéro ni un e-mail en clair.
        reason=mask_contacts(reason).text,
        created_at=datetime.now(UTC),
    )
    session.add(dispute)
    await session.flush()
    if had_review:
        # L'avis n'est plus public pendant le litige : note recalculée sans lui.
        await reviews_service.recalculate_artisan_rating(session, intervention.artisan_id)
    return OpenedDispute(
        intervention=to_intervention_out(intervention),
        trade_label=intervention.service_request.trade.label_fr,
        opened_by=role,
    )


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

    - `libere` (en faveur de l'artisan) : -> `terminee`, même enchaînement
      qu'une complétion (séquestre retenu libéré, versement du net ;
      espèces ou hors plateforme : commission due). Litige ouvert APRÈS les
      travaux : leur date de fin d'origine est conservée.
    - `rembourse` (en faveur du client) : -> `annulee` (arbitrage),
      commission annulée ; remboursement SEULEMENT des fonds réellement
      retenus en ligne (`settle_on_arbitration_for_client`). La demande
      redevient ouverte seulement si le litige a été ouvert pendant les
      travaux -- après leur fin, il n'y a plus de besoin à pourvoir.
    """
    intervention = await _get_for_update_or_404(session, intervention_id)
    dispute = intervention.dispute
    if intervention.status is not InterventionStatus.LITIGE or dispute is None:
        raise InterventionTransitionInvalideError()
    # `completed_at` n'est posé QUE par une confirmation de fin des travaux :
    # renseigné ici, le litige a été ouvert après la fin (fenêtre).
    opened_after_completion = intervention.completed_at is not None

    payout = None
    if outcome is DisputeOutcome.LIBERE:
        transition_intervention(intervention, InterventionStatus.TERMINEE)
        if not opened_after_completion:
            intervention.completed_at = datetime.now(UTC)
        payout = payments_service.settle_on_completion(session, intervention, settings=settings)
    else:
        transition_intervention(intervention, InterventionStatus.ANNULEE)
        mark_cancelled(
            intervention, by=Role.ADMIN, kind=InterventionCancellationKind.ARBITRAGE, reason=note
        )
        await payments_service.settle_on_arbitration_for_client(
            session, intervention, settings=settings, provider=provider
        )
        if not opened_after_completion:
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
            "opened_after_completion": opened_after_completion,
            "payout_id": payout.id if payout is not None else None,
        },
    )
    if intervention.review is not None:
        # Décision rendue, quelle qu'elle soit : l'avis redevient public.
        await reviews_service.recalculate_artisan_rating(session, intervention.artisan_id)
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
