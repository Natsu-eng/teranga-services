"""Versements aux artisans et réglages de versement (BUILD_PLAN.md §3.5).

Extraits de `app.services.payments` sans changement de logique : envoi d'un
versement dans sa propre transaction (idempotent, relançable), relance des
versements en attente, et choix du moyen de versement de l'artisan.
"""

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import SessionFactory
from app.models.enums import (
    PayoutStatus,
)
from app.models.user import User
from app.repositories import payments as payments_repository
from app.schemas.payments import (
    PayoutSettingsIn,
    PayoutSettingsOut,
)
from app.services.artisans import get_own_profile
from app.services.payment_providers.base import (
    PaymentProvider,
    PaymentProviderError,
    PayoutRequest,
)
from app.services.payments import _now

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ versement


async def dispatch_payout(
    session_factory: SessionFactory,
    payout_id: uuid.UUID,
    *,
    provider: PaymentProvider | None,
    settings: Settings,
) -> PayoutStatus | None:
    """Envoie un versement, dans sa PROPRE transaction (après le commit de la
    complétion) : un fournisseur indisponible ne fait jamais échouer la
    confirmation du client. Ne lève jamais ; un échec laisse le versement
    `echoue`, relançable (`scripts/dispatch_payouts.py`). Clé d'idempotence
    `payout-<id>` : relancer ne verse jamais deux fois."""
    try:
        async with session_factory() as session:
            payout = await payments_repository.get_payout_for_update(session, payout_id)
            if payout is None or payout.status is PayoutStatus.ENVOYE:
                return payout.status if payout is not None else None
            payout.attempts += 1
            payout.last_attempt_at = _now()
            try:
                if provider is None or provider.name != payout.provider:
                    raise PaymentProviderError(
                        f"fournisseur {payout.provider!r} indisponible pour ce versement"
                    )
                async with asyncio.timeout(settings.payment_provider_timeout_seconds):
                    operation = await provider.send_payout(
                        PayoutRequest(
                            amount_fcfa=payout.amount_fcfa,
                            currency=settings.payment_currency,
                            channel=payout.channel,
                            destination_phone=payout.destination_phone,
                            idempotency_key=f"payout-{payout.id}",
                            description="Téranga — versement de votre intervention",
                        )
                    )
            except (PaymentProviderError, TimeoutError) as exc:
                payout.status = PayoutStatus.ECHOUE
                payout.failure_reason = str(exc) or exc.__class__.__name__
                logger.warning("Versement %s en échec : %s", payout.id, payout.failure_reason)
            else:
                payout.status = PayoutStatus.ENVOYE
                payout.provider_ref = operation.reference
                payout.sent_at = _now()
                payout.failure_reason = None
            status = payout.status
            await session.commit()
            return status
    except Exception:
        logger.exception("Versement %s : erreur inattendue, à relancer.", payout_id)
        return None


async def dispatch_pending_payouts(
    session_factory: SessionFactory,
    *,
    provider: PaymentProvider | None,
    settings: Settings,
    limit: int,
) -> dict[PayoutStatus | None, int]:
    """Relance les versements en attente ou en échec (script d'exploitation)."""
    async with session_factory() as session:
        payout_ids = await payments_repository.list_payout_ids_to_dispatch(session, limit=limit)
    results: dict[PayoutStatus | None, int] = {}
    for payout_id in payout_ids:
        status = await dispatch_payout(
            session_factory, payout_id, provider=provider, settings=settings
        )
        results[status] = results.get(status, 0) + 1
    return results


class MoyenDeVersementIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="MOYEN_DE_VERSEMENT_INDISPONIBLE",
            message="Ce moyen de versement n'est pas disponible.",
            status_code=422,
        )


async def get_payout_settings(
    session: AsyncSession, *, user: User, settings: Settings
) -> PayoutSettingsOut:
    profile = await get_own_profile(session, user)
    return PayoutSettingsOut(
        channel=profile.payout_channel or settings.payout_default_channel,
        chosen=profile.payout_channel is not None,
        allowed_channels=list(settings.payout_allowed_channels),
        destination_phone=profile.user.phone,
    )


async def set_payout_settings(
    session: AsyncSession, *, user: User, payload: PayoutSettingsIn, settings: Settings
) -> PayoutSettingsOut:
    """Choix du moyen de versement ; s'applique aux versements créés ensuite
    (un versement déjà créé garde le moyen copié à sa création)."""
    if payload.channel not in settings.payout_allowed_channels:
        raise MoyenDeVersementIndisponibleError()
    profile = await get_own_profile(session, user)
    profile.payout_channel = payload.channel
    await session.flush()
    return await get_payout_settings(session, user=user, settings=settings)
