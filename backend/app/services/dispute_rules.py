"""Règles pures du litige : quand un problème peut être signalé (BUILD_PLAN.md
§3.5). Sans accès base : partagées par `app.services.disputes` (ouverture,
qui fait foi) et par la réponse API (`dispute_deadline`), pour que l'écran
n'affiche jamais un bouton que le serveur refuserait.

- **Pendant les travaux** (`en_cours`) : toujours.
- **Après la fin des travaux** (`terminee`) : pendant DISPUTE_WINDOW_HOURS
  après la confirmation (`completed_at`), si aucun litige n'a déjà eu lieu
  et si aucun paiement en ligne n'a été versé à l'artisan (Téranga ne
  détient plus les fonds : rien à geler). Le versement différé du séquestre
  pendant la fenêtre viendra avec l'agrégateur.
- Jamais ailleurs (proposée, acceptée, annulée, déjà en litige).
"""

from datetime import datetime, timedelta
from enum import StrEnum

from app.models.enums import InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.services.payment_summary import current_payment


class DisputeRefusal(StrEnum):
    """Pourquoi un signalement est refusé (chaque cas a son erreur métier)."""

    TRANSITION = "transition"
    ALREADY_DISPUTED = "already_disputed"
    WINDOW_ELAPSED = "window_elapsed"
    ONLINE_PAYMENT_RELEASED = "online_payment_released"


def dispute_deadline(intervention: Intervention, *, window_hours: int) -> datetime | None:
    """Fin de la fenêtre de signalement après les travaux, ou None (pas
    terminée, fenêtre désactivée)."""
    if (
        intervention.status is not InterventionStatus.TERMINEE
        or intervention.completed_at is None
        or window_hours <= 0
    ):
        return None
    return intervention.completed_at + timedelta(hours=window_hours)


def dispute_refusal(
    intervention: Intervention, *, window_hours: int, now: datetime
) -> DisputeRefusal | None:
    """None si un litige peut être ouvert maintenant, sinon la raison du refus."""
    if intervention.dispute is not None:
        return DisputeRefusal.ALREADY_DISPUTED
    if intervention.status is InterventionStatus.EN_COURS:
        return None
    if intervention.status is not InterventionStatus.TERMINEE:
        return DisputeRefusal.TRANSITION
    deadline = dispute_deadline(intervention, window_hours=window_hours)
    if deadline is None or now >= deadline:
        return DisputeRefusal.WINDOW_ELAPSED
    payment = current_payment(intervention)
    if payment is not None and payment.status is PaymentStatus.LIBERE:
        return DisputeRefusal.ONLINE_PAYMENT_RELEASED
    return None


def open_dispute_deadline(
    intervention: Intervention, *, window_hours: int, now: datetime
) -> datetime | None:
    """Échéance à AFFICHER à côté du bouton « Signaler un problème » après les
    travaux : seulement si le signalement est réellement possible."""
    if intervention.status is not InterventionStatus.TERMINEE:
        return None
    if dispute_refusal(intervention, window_hours=window_hours, now=now) is not None:
        return None
    return dispute_deadline(intervention, window_hours=window_hours)
