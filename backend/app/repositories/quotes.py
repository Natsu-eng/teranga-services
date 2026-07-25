"""Accès données pour `quote` (BUILD_PLAN.md §2.2, §3.2, §6 Lot 12b).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation, calcul du total) -- voir `app.services.quotes`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import Intervention, Quote


async def create_or_replace_quote(
    session: AsyncSession,
    *,
    intervention: Intervention,
    labor_fcfa: int,
    materials_fcfa: int,
    total_fcfa: int,
) -> Quote:
    """Pose le devis de `intervention`, en remplaçant l'éventuel devis
    existant plutôt que d'en empiler un second (BUILD_PLAN.md §6 Lot 12b) :
    `quote.intervention_id` est UNIQUE en base (1:1, Lot 7) -- un re-devis
    après refus remplace donc physiquement l'ancienne ligne, il ne la
    complète pas.

    Le DELETE de l'éventuel devis existant est flushé séparément, AVANT
    l'ajout du nouveau : dans un flush unique, SQLAlchemy exécute les
    INSERT/UPDATE avant les DELETE, ce qui violerait la contrainte UNIQUE
    `intervention_id` (les deux lignes, ancienne et nouvelle, la partagent le
    temps du flush) si les deux mutations n'étaient pas séparées ainsi.
    """
    if intervention.quote is not None:
        await session.delete(intervention.quote)
        await session.flush()

    quote = Quote(
        intervention=intervention,
        labor_fcfa=labor_fcfa,
        materials_fcfa=materials_fcfa,
        total_fcfa=total_fcfa,
    )
    session.add(quote)
    await session.flush()
    return quote
