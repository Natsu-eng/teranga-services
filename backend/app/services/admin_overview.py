"""Vue d'ensemble du back-office : chiffres dérivés des données réelles.

Une requête d'agrégat par famille (GROUP BY), jamais un chiffre stocké à
part qui pourrait diverger ; chaque statut absent vaut 0.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanProfile, Verification
from app.models.enums import (
    ArtisanVerifiedStatus,
    InterventionStatus,
    PaymentStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
    ReviewStatus,
    Role,
    VerificationStatus,
)
from app.models.intervention import Intervention, InterventionDispute
from app.models.payment import Payment, PlatformFee
from app.models.review import Review
from app.models.user import User
from app.schemas.admin_overview import (
    AdminOverviewOut,
    ArtisanCountsOut,
    InterventionCountsOut,
    MoneyOut,
    UserCountsOut,
)


async def _grouped(session: AsyncSession, stmt: Select[Any]) -> dict[str, int]:
    """`{valeur: total}` pour un SELECT (clé, agrégat) GROUP BY clé."""
    rows: Sequence[Any] = (await session.execute(stmt)).all()
    return {
        (key.value if isinstance(key, Enum) else str(key)): int(total or 0) for key, total in rows
    }


async def get_overview(session: AsyncSession) -> AdminOverviewOut:
    artisans = await _grouped(
        session,
        select(ArtisanProfile.verified_status, func.count())
        .where(ArtisanProfile.deleted_at.is_(None))
        .group_by(ArtisanProfile.verified_status),
    )
    users = await _grouped(
        session,
        select(User.role, func.count()).where(User.deleted_at.is_(None)).group_by(User.role),
    )
    interventions = await _grouped(
        session,
        select(Intervention.status, func.count()).group_by(Intervention.status),
    )
    payments = await _grouped(
        session,
        select(Payment.status, func.sum(Payment.amount_fcfa)).group_by(Payment.status),
    )
    # Commissions : statut, et si les travaux sont terminés (une commission
    # « due » sur travaux terminés est due par l'artisan ; sur travaux en
    # cours, elle sera prélevée à la libération du séquestre).
    fee_rows = (
        await session.execute(
            select(PlatformFee.status, Intervention.status, func.sum(PlatformFee.amount_fcfa))
            .join(Intervention, Intervention.id == PlatformFee.intervention_id)
            .where(PlatformFee.kind == PlatformFeeKind.COMMISSION)
            .group_by(PlatformFee.status, Intervention.status)
        )
    ).all()
    collected = due = pending = 0
    for status, intervention_status, total in fee_rows:
        amount = int(total or 0)
        completed = intervention_status is InterventionStatus.TERMINEE
        if status is PlatformFeeStatus.COLLECTEE:
            collected += amount
        elif status is PlatformFeeStatus.DUE and completed:
            due += amount
        elif status is PlatformFeeStatus.DUE:
            pending += amount

    pending_verifications = (
        await session.execute(
            select(func.count())
            .select_from(Verification)
            .where(Verification.status == VerificationStatus.PENDING)
        )
    ).scalar_one()
    suspended_artisans = (
        await session.execute(
            select(func.count())
            .select_from(ArtisanProfile)
            .where(ArtisanProfile.deleted_at.is_(None), ArtisanProfile.suspended_at.is_not(None))
        )
    ).scalar_one()
    reported_reviews = (
        await session.execute(
            select(func.count()).select_from(Review).where(Review.status == ReviewStatus.SIGNALE)
        )
    ).scalar_one()
    open_disputes = (
        await session.execute(
            select(func.count())
            .select_from(InterventionDispute)
            .join(Intervention, Intervention.id == InterventionDispute.intervention_id)
            .where(
                InterventionDispute.resolved_at.is_(None),
                Intervention.status == InterventionStatus.LITIGE,
            )
        )
    ).scalar_one()

    in_escrow = payments.get(PaymentStatus.RETENU.value, 0)
    released = payments.get(PaymentStatus.LIBERE.value, 0)
    cash = payments.get(PaymentStatus.REUSSI.value, 0)
    return AdminOverviewOut(
        artisans=ArtisanCountsOut(
            total=sum(artisans.values()),
            **{status.value: artisans.get(status.value, 0) for status in ArtisanVerifiedStatus},
            suspended=suspended_artisans,
        ),
        users=UserCountsOut(
            clients=users.get(Role.CLIENT.value, 0),
            artisans=users.get(Role.ARTISAN.value, 0),
            admins=users.get(Role.ADMIN.value, 0),
        ),
        interventions=InterventionCountsOut(
            **{status.value: interventions.get(status.value, 0) for status in InterventionStatus}
        ),
        money=MoneyOut(
            in_escrow_fcfa=in_escrow,
            released_fcfa=released,
            cash_fcfa=cash,
            refunded_fcfa=payments.get(PaymentStatus.REMBOURSE.value, 0),
            business_volume_fcfa=in_escrow + released + cash,
            commission_collected_fcfa=collected,
            commission_due_fcfa=due,
            commission_pending_fcfa=pending,
        ),
        pending_verifications=pending_verifications,
        open_disputes=open_disputes,
        reported_reviews=reported_reviews,
        generated_at=datetime.now(UTC),
    )
