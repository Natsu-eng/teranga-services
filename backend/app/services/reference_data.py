"""Données de RÉFÉRENCE indispensables au fonctionnement, en dev comme en
production (DEPLOYMENT.md) : les métiers proposés et un taux de commission
global initial.

Distinctes des données de DÉMONSTRATION de `scripts/seed.py` (faux
artisans, faux avis, client de démo), qui ne doivent jamais atteindre la
production. Toutes les fonctions sont idempotentes (get-or-create par clé
naturelle) : relancer ne duplique rien et ne modifie rien d'existant.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commission import CommissionRate
from app.models.trade import Trade

# (code, libellé, ordre d'affichage). Le code est la clé stable utilisée par
# l'API et le triage IA ; le libellé peut évoluer sans migration.
TRADES: list[tuple[str, str, int]] = [
    ("plomberie", "Plomberie", 1),
    ("electricite", "Électricité", 2),
    ("climatisation", "Climatisation", 3),
    ("menuiserie", "Menuiserie", 4),
    ("maconnerie", "Maçonnerie", 5),
]

# Taux global par défaut (décision produit actée, BUILD_PLAN.md §7) : 10 %.
# Modifiable ensuite par l'ajout d'un taux daté dans le back-office.
DEFAULT_COMMISSION_RATE_BPS = 1000


async def ensure_trade(
    session: AsyncSession, code: str, label_fr: str, sort_order: int
) -> tuple[Trade, bool]:
    """Le métier `code` (créé s'il manque). Renvoie (métier, créé ?)."""
    trade = (await session.execute(select(Trade).where(Trade.code == code))).scalar_one_or_none()
    if trade is not None:
        return trade, False
    trade = Trade(code=code, label_fr=label_fr, sort_order=sort_order, is_active=True)
    session.add(trade)
    await session.flush()
    return trade, True


async def ensure_trades(session: AsyncSession) -> dict[str, tuple[Trade, bool]]:
    return {
        code: await ensure_trade(session, code, label_fr, sort_order)
        for code, label_fr, sort_order in TRADES
    }


async def ensure_default_commission_rate(
    session: AsyncSession, *, rate_bps: int = DEFAULT_COMMISSION_RATE_BPS
) -> tuple[CommissionRate, bool]:
    """Le taux GLOBAL ouvert (créé s'il n'en existe aucun). Un taux global
    déjà en place n'est jamais modifié : la grille ne s'édite pas, on y
    ajoute un taux daté (back-office)."""
    existing = (
        await session.execute(
            select(CommissionRate).where(
                CommissionRate.trade_id.is_(None),
                CommissionRate.tier.is_(None),
                CommissionRate.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    rate = CommissionRate(
        rate_bps=rate_bps, trade_id=None, tier=None, effective_from=datetime.now(UTC)
    )
    session.add(rate)
    await session.flush()
    return rate, True
