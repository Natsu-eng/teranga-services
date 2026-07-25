"""Orchestration du triage IA (`POST /api/v1/ai/analyze`, BUILD_PLAN.md §3.2,
§6 Lot 11) : sélectionne le fournisseur actif, durcit sa sortie (schéma déjà
validé par `TriageResult` + existence réelle du métier en base), et retombe
sur l'heuristique à la moindre anomalie -- jamais d'erreur 500 renvoyée au
client pour un incident IA (c'est le durcissement pointé par l'audit du
Lot 0 sur l'ancien endpoint Express, qui ne validait rien).

**Décision actée sur `trade_code` inconnu** : rejet + fallback heuristique,
jamais de mapping approximatif vers le métier "le plus proche" -- un
mapping flou masquerait une dérive du prompt/modèle plutôt que de la rendre
visible dans les logs.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.repositories import trades as trades_repository
from app.schemas.ai_triage import TriageResult
from app.services.ai_triage_providers import (
    AiTriageProviderError,
    HeuristicTriageProvider,
    get_ai_triage_provider,
)

logger = logging.getLogger(__name__)


async def analyze_problem(
    session: AsyncSession, description: str, *, settings: Settings
) -> TriageResult:
    provider = get_ai_triage_provider(settings)

    if isinstance(provider, HeuristicTriageProvider):
        # Filet déjà de confiance : ses trade_code sont un ensemble fixe et
        # contrôlé par ce module (_QUOTE_BY_TRADE), pas besoin d'un
        # aller-retour DB sur le chemin par défaut.
        return await provider.analyze(description)

    try:
        result = await provider.analyze(description)
    except AiTriageProviderError as exc:
        logger.warning(
            "Fournisseur IA %s indisponible (%s) -- fallback heuristique.",
            type(provider).__name__,
            exc,
        )
        return await HeuristicTriageProvider().analyze(description)

    trade = await trades_repository.get_active_trade_by_code(session, result.trade_code)
    if trade is None:
        logger.warning(
            "Le fournisseur IA a renvoyé un trade_code inconnu ou inactif (%r) -- "
            "fallback heuristique.",
            result.trade_code,
        )
        return await HeuristicTriageProvider().analyze(description)
    return result
