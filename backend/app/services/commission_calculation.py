"""Calcul de la commission Téranga (BUILD_PLAN.md §7, §3.5).

Fonction **pure** : aucune base, aucun réglage lu ici -- le taux (figé sur
l'intervention à sa création, jamais le taux courant) et la règle d'arrondi
sont passés en paramètres par l'appelant (`app.services.payments`).

**Uniquement des entiers.** Les montants sont en FCFA entiers (le franc CFA
n'a pas de subdivision en usage), le taux en points de base
(`rate_bps` : 1 000 = 10 %). Le produit `montant × taux` est calculé en
entier exact puis divisé par 10 000 avec une règle d'arrondi EXPLICITE :
jamais de float, donc jamais d'écart d'un franc selon la plateforme.

**Règle d'arrondi par défaut : `floor` (troncature vers le bas), en faveur
de l'artisan.** La commission ne dépasse jamais le taux annoncé, même d'une
fraction de franc ; l'écart maximal est de 1 FCFA par intervention, au
détriment de Téranga. Le net artisan est TOUJOURS calculé par soustraction
(`montant - commission`) : la somme `commission + net` vaut le montant au
franc près, par construction, quelle que soit la règle choisie.
"""

from dataclasses import dataclass
from typing import Literal

# Un taux en points de base s'exprime sur 10 000 (1 bps = 0,01 %).
BPS_DENOMINATOR = 10_000

CommissionRounding = Literal["floor", "half_up", "ceil"]


@dataclass(frozen=True)
class CommissionBreakdown:
    """Décomposition d'un montant : ce que paie le client (`gross_fcfa`), ce
    que prélève Téranga (`commission_fcfa`), ce que touche l'artisan
    (`net_fcfa`)."""

    gross_fcfa: int
    rate_bps: int
    commission_fcfa: int
    net_fcfa: int


def _divide(numerator: int, rounding: CommissionRounding) -> int:
    """`numerator / BPS_DENOMINATOR` arrondi selon `rounding`, en entiers seuls
    (numérateur toujours positif ou nul ici)."""
    if rounding == "floor":
        return numerator // BPS_DENOMINATOR
    if rounding == "ceil":
        return -(-numerator // BPS_DENOMINATOR)
    # half_up : la demi-unité (x,5 FCFA) est arrondie au franc supérieur.
    return (numerator + BPS_DENOMINATOR // 2) // BPS_DENOMINATOR


def compute_commission(
    amount_fcfa: int, rate_bps: int, *, rounding: CommissionRounding = "floor"
) -> CommissionBreakdown:
    """Commission et net artisan pour `amount_fcfa` au taux `rate_bps`.

    Lève `ValueError` sur une entrée hors domaine (montant négatif, taux hors
    [0, 10 000], valeur non entière -- `bool` compris, qui est un `int` en
    Python) : un calcul financier n'interprète jamais une entrée douteuse.
    """
    for name, value in (("amount_fcfa", amount_fcfa), ("rate_bps", rate_bps)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} doit être un entier (reçu {value!r}).")
    if amount_fcfa < 0:
        raise ValueError("amount_fcfa ne peut pas être négatif.")
    if not 0 <= rate_bps <= BPS_DENOMINATOR:
        raise ValueError(f"rate_bps doit être compris entre 0 et {BPS_DENOMINATOR}.")

    commission = _divide(amount_fcfa * rate_bps, rounding)
    return CommissionBreakdown(
        gross_fcfa=amount_fcfa,
        rate_bps=rate_bps,
        commission_fcfa=commission,
        net_fcfa=amount_fcfa - commission,
    )
