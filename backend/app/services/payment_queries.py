"""Consultation des paiements (BUILD_PLAN.md §3.5) : historique du client
et gains de l'artisan. Lecture seule, extraite de `app.services.payments`
sans changement de logique.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import interventions as interventions_repository
from app.repositories import payments as payments_repository
from app.schemas.pagination import Page
from app.schemas.payments import (
    ArtisanEarningsOut,
    ClientPaymentOut,
    EarningItemOut,
    EarningsTotalsOut,
)
from app.services.artisans import PageHorsBornesError
from app.services.identity import public_display_name
from app.services.payment_summary import (
    online_payment_available,
)
from app.services.payment_summary import summarize as summarize_payment

# ------------------------------------------------------------------ consultation


def _page_bounds(page: int, page_size: int, settings: Settings) -> tuple[int, int]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)
    return resolved, (page - 1) * resolved


async def list_client_payments(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[ClientPaymentOut]:
    resolved, offset = _page_bounds(page, page_size, settings)
    payments = await payments_repository.list_payments_for_client(
        session, user.id, limit=resolved, offset=offset
    )
    total = await payments_repository.count_payments_for_client(session, user.id)
    items = [
        ClientPaymentOut(
            id=payment.id,
            intervention_id=payment.intervention_id,
            trade_label=payment.intervention.service_request.trade.label_fr,
            artisan_name=public_display_name(payment.intervention.artisan.user.full_name),
            amount_fcfa=payment.amount_fcfa,
            channel=payment.channel,
            status=payment.status,
            created_at=payment.created_at,
            paid_at=payment.paid_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
        )
        for payment in payments
    ]
    return Page.of(items, page=page, page_size=resolved, total=total)


async def artisan_earnings(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> ArtisanEarningsOut:
    """Gains de l'artisan courant : synthèse + détail par intervention, avec
    pour chacune le total, la commission prélevée et le net."""
    resolved, offset = _page_bounds(page, page_size, settings)
    artisan_id = await artisans_repository.get_artisan_profile_id_by_user_id(session, user.id)
    if artisan_id is None:
        return ArtisanEarningsOut(
            totals=EarningsTotalsOut(
                paid_out_fcfa=0,
                payout_pending_fcfa=0,
                in_escrow_fcfa=0,
                commission_collected_fcfa=0,
                cash_received_fcfa=0,
                commission_due_fcfa=0,
            ),
            items=[],
            pagination=Page.of([], page=page, page_size=resolved, total=0).pagination,
        )

    totals = await payments_repository.artisan_earnings_totals(session, artisan_id)
    ids = await payments_repository.list_paid_intervention_ids_for_artisan(
        session, artisan_id, limit=resolved, offset=offset
    )
    total = await payments_repository.count_paid_interventions_for_artisan(session, artisan_id)
    interventions = await interventions_repository.list_by_ids(session, ids)
    items = []
    for intervention in interventions:
        summary = summarize_payment(
            intervention,
            rounding=settings.commission_rounding,
            online_available=online_payment_available(settings),
        )
        if summary is None:
            continue
        items.append(
            EarningItemOut(
                intervention_id=intervention.id,
                trade_label=intervention.service_request.trade.label_fr,
                client_name=public_display_name(intervention.client.full_name),
                intervention_status=intervention.status,
                payment=summary,
            )
        )
    return ArtisanEarningsOut(
        totals=EarningsTotalsOut(**totals),
        items=items,
        pagination=Page.of(items, page=page, page_size=resolved, total=total).pagination,
    )
