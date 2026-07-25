"""Accès données pour la résolution du taux de commission en vigueur.

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
-- voir `app.services.commission` pour ça.
"""

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commission import CommissionRate


async def find_effective_rate(
    session: AsyncSession, *, trade_id: uuid.UUID, at: datetime
) -> CommissionRate | None:
    """Le taux le plus spécifique en vigueur à `at` pour `trade_id`.

    Portée "tous paliers" uniquement (`tier IS NULL`) -- la granularité par
    palier d'abonnement n'est pas résolue par cette fonction (hors périmètre
    de ce lot). Un taux ciblé sur le métier (`trade_id` == celui demandé)
    prime toujours sur un taux global (`trade_id IS NULL`), même si les deux
    sont en vigueur simultanément -- c'est tout l'intérêt de la portée
    métier. À spécificité égale, la contrainte d'exclusion de
    `commission_rate` (BUILD_PLAN.md §2.2) garantit qu'au plus une ligne est
    en vigueur à un instant donné pour un même couple (trade_id, tier) ;
    `effective_from DESC` ne sert donc que de garde-fou de robustesse, pas de
    départage attendu en pratique.
    """
    stmt = (
        select(CommissionRate)
        .where(
            or_(CommissionRate.trade_id == trade_id, CommissionRate.trade_id.is_(None)),
            CommissionRate.tier.is_(None),
            CommissionRate.effective_from <= at,
            or_(CommissionRate.effective_to.is_(None), CommissionRate.effective_to > at),
        )
        # trade_id.is_(None) vaut False pour une ligne spécifique et True pour
        # une ligne globale -- en ASC, False (spécifique) sort avant True
        # (global), donc le taux ciblé prime sans jamais l'exprimer en dur.
        .order_by(CommissionRate.trade_id.is_(None), CommissionRate.effective_from.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
