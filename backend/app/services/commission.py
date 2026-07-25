"""Résolution du taux de commission en vigueur (BUILD_PLAN.md §2.2, §7).

Le taux n'est **jamais en dur** : toute intervention doit figer, à sa
création, le `commission_rate_id` réellement en vigueur pour son métier à cet
instant -- voir `app.services.interventions`. Ce module est la seule source
de vérité pour cette résolution.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.commission import CommissionRate
from app.repositories import commission as commission_repository


class CommissionRateIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COMMISSION_RATE_INTROUVABLE",
            message="Aucun taux de commission n'est en vigueur pour ce métier à cette date.",
            status_code=500,
        )


async def resolve_effective_commission_rate(
    session: AsyncSession, *, trade_id: uuid.UUID, at: datetime | None = None
) -> CommissionRate:
    """Le `commission_rate` applicable à `trade_id` à l'instant `at` (défaut : maintenant).

    Lève `CommissionRateIntrouvableError` si aucun taux ne couvre cet instant
    -- jamais de valeur par défaut silencieuse (BUILD_PLAN.md §2.2) : un taux
    manquant est une erreur de configuration à corriger, pas une commission à
    0 % inventée.
    """
    resolved_at = at or datetime.now(UTC)
    rate = await commission_repository.find_effective_rate(
        session, trade_id=trade_id, at=resolved_at
    )
    if rate is None:
        raise CommissionRateIntrouvableError()
    return rate
