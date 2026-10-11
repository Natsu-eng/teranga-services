"""Accès données des paiements (BUILD_PLAN.md §3.5).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(règles d'exigibilité, autorisation, transitions) -- voir
`app.services.payments` pour ça.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.artisan import ArtisanProfile
from app.models.enums import (
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PayoutStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
)
from app.models.intervention import Intervention, InterventionDispute
from app.models.payment import Payment, PaymentEvent, Payout, PlatformFee
from app.models.request import ServiceRequest


async def find_payment_by_provider_ref(
    session: AsyncSession, *, provider: str, provider_ref: str
) -> Payment | None:
    stmt = select(Payment).where(Payment.provider == provider, Payment.provider_ref == provider_ref)
    return (await session.execute(stmt)).scalar_one_or_none()


async def record_event(
    session: AsyncSession, *, provider: str, event_id: str, event_type: str
) -> uuid.UUID | None:
    """Journalise un webhook ; renvoie son identifiant, ou `None` s'il a DÉJÀ
    été reçu (même fournisseur, même event id).

    `INSERT ... ON CONFLICT DO NOTHING` sur la contrainte unique : c'est la
    base qui tranche, y compris quand deux livraisons identiques arrivent en
    même temps (la seconde attend la fin de la première transaction puis ne
    trouve rien à insérer) -- jamais de double traitement.
    """
    stmt = (
        insert(PaymentEvent)
        .values(
            id=uuid.uuid4(),
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            outcome="en_cours",
        )
        .on_conflict_do_nothing(constraint="uq_payment_event_provider_event_id")
        .returning(PaymentEvent.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def set_event_outcome(
    session: AsyncSession, *, event_row_id: uuid.UUID, outcome: str, payment_id: uuid.UUID | None
) -> None:
    event = await session.get(PaymentEvent, event_row_id)
    if event is not None:
        event.outcome = outcome
        event.payment_id = payment_id


async def get_payout_for_update(session: AsyncSession, payout_id: uuid.UUID) -> Payout | None:
    stmt = (
        select(Payout)
        .where(Payout.id == payout_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_payout_ids_to_dispatch(session: AsyncSession, *, limit: int) -> list[uuid.UUID]:
    """Versements jamais partis ou en échec, du plus ancien au plus récent."""
    stmt = (
        select(Payout.id)
        .where(Payout.status.in_((PayoutStatus.EN_ATTENTE, PayoutStatus.ECHOUE)))
        .order_by(Payout.created_at, Payout.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def _with_context(stmt: Select[tuple[Payment]]) -> Select[tuple[Payment]]:
    return stmt.options(
        joinedload(Payment.intervention)
        .joinedload(Intervention.service_request)
        .joinedload(ServiceRequest.trade),
        joinedload(Payment.intervention)
        .joinedload(Intervention.artisan)
        .joinedload(ArtisanProfile.user),
    )


async def list_payments_for_client(
    session: AsyncSession, client_id: uuid.UUID, *, limit: int, offset: int
) -> list[Payment]:
    stmt = _with_context(
        select(Payment)
        .join(Intervention, Intervention.id == Payment.intervention_id)
        .where(Intervention.client_id == client_id)
        .order_by(Payment.created_at.desc(), Payment.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_payments_for_client(session: AsyncSession, client_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Payment)
        .join(Intervention, Intervention.id == Payment.intervention_id)
        .where(Intervention.client_id == client_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def list_paid_intervention_ids_for_artisan(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int, offset: int
) -> list[uuid.UUID]:
    """Interventions de l'artisan qui ont au moins un paiement, la plus
    récemment payée d'abord (historique de ses gains)."""
    last_payment = func.max(Payment.created_at)
    stmt = (
        select(Intervention.id)
        .join(Payment, Payment.intervention_id == Intervention.id)
        .where(Intervention.artisan_id == artisan_id)
        .group_by(Intervention.id)
        .order_by(last_payment.desc(), Intervention.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_paid_interventions_for_artisan(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count(func.distinct(Intervention.id)))
        .select_from(Intervention)
        .join(Payment, Payment.intervention_id == Intervention.id)
        .where(Intervention.artisan_id == artisan_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def list_disputed_intervention_ids(
    session: AsyncSession, *, resolved: bool, limit: int, offset: int
) -> list[uuid.UUID]:
    """Litiges ouverts (du plus ancien au plus récent : premier ouvert,
    premier tranché) ou tranchés (du plus récent au plus ancien)."""
    stmt = select(InterventionDispute.intervention_id)
    if resolved:
        stmt = stmt.where(InterventionDispute.resolved_at.is_not(None)).order_by(
            InterventionDispute.resolved_at.desc(), InterventionDispute.id
        )
    else:
        stmt = (
            stmt.join(Intervention, Intervention.id == InterventionDispute.intervention_id)
            .where(
                InterventionDispute.resolved_at.is_(None),
                Intervention.status == InterventionStatus.LITIGE,
            )
            .order_by(InterventionDispute.created_at, InterventionDispute.id)
        )
    return list((await session.execute(stmt.limit(limit).offset(offset))).scalars().all())


async def count_disputes(session: AsyncSession, *, resolved: bool) -> int:
    stmt = select(func.count()).select_from(InterventionDispute)
    if resolved:
        stmt = stmt.where(InterventionDispute.resolved_at.is_not(None))
    else:
        stmt = stmt.join(
            Intervention, Intervention.id == InterventionDispute.intervention_id
        ).where(
            InterventionDispute.resolved_at.is_(None),
            Intervention.status == InterventionStatus.LITIGE,
        )
    return (await session.execute(stmt)).scalar_one()


async def artisan_earnings_totals(session: AsyncSession, artisan_id: uuid.UUID) -> dict[str, int]:
    """Synthèse des gains d'un artisan, en FCFA (voir `EarningsTotalsOut`)."""

    async def total(stmt: Select[tuple[int]]) -> int:
        # SUM() renvoie NULL sur un ensemble vide : 0 FCFA, jamais None.
        return int((await session.execute(stmt)).scalar_one() or 0)

    of_artisan = Intervention.artisan_id == artisan_id
    payout_sum = select(func.sum(Payout.amount_fcfa)).where(Payout.artisan_id == artisan_id)
    commission = (
        select(func.sum(PlatformFee.amount_fcfa))
        .join(Intervention, Intervention.id == PlatformFee.intervention_id)
        .where(of_artisan, PlatformFee.kind == PlatformFeeKind.COMMISSION)
    )
    fee_amount = (
        select(PlatformFee.amount_fcfa)
        .where(
            PlatformFee.intervention_id == Payment.intervention_id,
            PlatformFee.kind == PlatformFeeKind.COMMISSION,
        )
        .scalar_subquery()
    )
    return {
        "paid_out_fcfa": await total(payout_sum.where(Payout.status == PayoutStatus.ENVOYE)),
        "payout_pending_fcfa": await total(
            payout_sum.where(Payout.status.in_((PayoutStatus.EN_ATTENTE, PayoutStatus.ECHOUE)))
        ),
        # Net encore en séquestre : montant retenu moins la commission qui
        # sera prélevée à la libération.
        "in_escrow_fcfa": await total(
            select(func.sum(Payment.amount_fcfa - func.coalesce(fee_amount, 0)))
            .join(Intervention, Intervention.id == Payment.intervention_id)
            .where(of_artisan, Payment.status == PaymentStatus.RETENU)
        ),
        "commission_collected_fcfa": await total(
            commission.where(PlatformFee.status == PlatformFeeStatus.COLLECTEE)
        ),
        # Espèces : comptées une fois les travaux confirmés terminés.
        "cash_received_fcfa": await total(
            select(func.sum(Payment.amount_fcfa))
            .join(Intervention, Intervention.id == Payment.intervention_id)
            .where(
                of_artisan,
                Payment.channel == PaymentChannel.CASH,
                Payment.status == PaymentStatus.REUSSI,
                Intervention.status == InterventionStatus.TERMINEE,
            )
        ),
        # Commission non prélevée sur des travaux terminés (espèces ou
        # règlement hors plateforme) : due par l'artisan.
        "commission_due_fcfa": await total(
            commission.where(
                PlatformFee.status == PlatformFeeStatus.DUE,
                Intervention.status == InterventionStatus.TERMINEE,
            )
        ),
    }
