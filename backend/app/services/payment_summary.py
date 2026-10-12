"""Résumé financier d'une intervention (BUILD_PLAN.md §3.5).

Assemblé depuis une intervention déjà chargée (paiements, commission,
versement eager-loadés) : aucune requête ici, aucune décision -- seulement
la lecture fidèle de l'état enregistré.
"""

from datetime import UTC, datetime

from app.core.config import Settings
from app.models.enums import PaymentStatus, PlatformFeeKind
from app.models.intervention import Intervention
from app.models.payment import ACTIVE_PAYMENT_STATUSES, Payment, PlatformFee
from app.schemas.payments import CommissionOut, PaymentSummaryOut, PayoutOut
from app.services.commission_calculation import CommissionRounding, compute_commission


def current_payment(intervention: Intervention) -> Payment | None:
    """Le paiement qui fait foi : le paiement vivant s'il existe (au plus un,
    garanti par la base), sinon le plus récent (remboursé, échoué...)."""
    active = [p for p in intervention.payments if p.status in ACTIVE_PAYMENT_STATUSES]
    if active:
        return active[0]
    if not intervention.payments:
        return None
    return max(intervention.payments, key=lambda p: (p.created_at, str(p.id)))


def commission_fee(intervention: Intervention) -> PlatformFee | None:
    return next(
        (fee for fee in intervention.platform_fees if fee.kind is PlatformFeeKind.COMMISSION),
        None,
    )


def is_checkout_open(payment: Payment, *, now: datetime | None = None) -> bool:
    """Vrai si la page de paiement de ce paiement peut encore être payée."""
    return (
        payment.status is PaymentStatus.EN_ATTENTE
        and payment.checkout_expires_at is not None
        and payment.checkout_expires_at > (now or datetime.now(UTC))
    )


def online_payment_available(settings: Settings) -> bool:
    """Vrai si un fournisseur de paiement en ligne est actif et propose au
    moins un moyen. Faux avec PAYMENT_PROVIDER=disabled (espèces seulement)."""
    return settings.payment_provider != "disabled" and bool(settings.payment_online_channels)


def summarize(
    intervention: Intervention, *, rounding: CommissionRounding, online_available: bool
) -> PaymentSummaryOut | None:
    """`None` tant qu'aucun montant n'est convenu (pas de devis accepté)."""
    amount = intervention.agreed_amount_fcfa
    if amount is None:
        return None

    fee = commission_fee(intervention)
    rate_bps = intervention.commission_rate.rate_bps
    # Commission enregistrée = montant qui fait foi ; sinon estimation au
    # taux FIGÉ de l'intervention (jamais le taux courant).
    commission_fcfa = (
        fee.amount_fcfa
        if fee is not None
        else compute_commission(amount, rate_bps, rounding=rounding).commission_fcfa
    )
    payment = current_payment(intervention)
    payout = intervention.payouts[0] if intervention.payouts else None
    checkout_open = payment is not None and is_checkout_open(payment)

    return PaymentSummaryOut(
        amount_fcfa=amount,
        commission=CommissionOut(
            rate_bps=rate_bps,
            amount_fcfa=commission_fcfa,
            status=fee.status if fee is not None else None,
        ),
        net_fcfa=amount - commission_fcfa,
        status=payment.status if payment is not None else None,
        channel=payment.channel if payment is not None else None,
        checkout_url=payment.checkout_url if payment is not None and checkout_open else None,
        checkout_expires_at=(
            payment.checkout_expires_at if payment is not None and checkout_open else None
        ),
        paid_at=payment.paid_at if payment is not None else None,
        released_at=payment.released_at if payment is not None else None,
        refunded_at=payment.refunded_at if payment is not None else None,
        payout=(
            PayoutOut(
                status=payout.status,
                amount_fcfa=payout.amount_fcfa,
                channel=payout.channel,
                sent_at=payout.sent_at,
            )
            if payout is not None
            else None
        ),
        online_available=online_available,
    )
