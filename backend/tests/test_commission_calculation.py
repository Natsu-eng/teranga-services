"""Calcul pur de la commission (`app.services.commission_calculation`).

Aucune base : la fonction ne dépend que du montant, du taux figé et de la
règle d'arrondi.
"""

from typing import cast

import pytest

from app.services.commission_calculation import (
    BPS_DENOMINATOR,
    CommissionRounding,
    compute_commission,
)

ROUNDINGS: tuple[CommissionRounding, ...] = ("floor", "half_up", "ceil")


@pytest.mark.parametrize(
    ("amount", "rate_bps", "commission", "net"),
    [
        (12_000, 1_000, 1_200, 10_800),  # 10 % d'un devis courant
        (15_000, 1_000, 1_500, 13_500),
        (1_000_000, 750, 75_000, 925_000),  # 7,5 % d'un gros chantier
        (12_345, 1_000, 1_234, 11_111),  # 1 234,5 -> 1 234 (vers le bas)
        (9_999, 1_250, 1_249, 8_750),  # 1 249,875 -> 1 249
        (1, 1_000, 0, 1),  # 0,1 FCFA -> 0 : l'artisan garde tout
        (0, 1_000, 0, 0),
        (5_000, 0, 0, 5_000),  # taux nul
        (5_000, BPS_DENOMINATOR, 5_000, 0),  # taux de 100 %
    ],
)
def test_floor_rounding_never_exceeds_the_announced_rate(
    amount: int, rate_bps: int, commission: int, net: int
) -> None:
    result = compute_commission(amount, rate_bps, rounding="floor")

    assert result.commission_fcfa == commission
    assert result.net_fcfa == net
    assert result.gross_fcfa == amount
    assert result.rate_bps == rate_bps


def test_floor_is_the_default_rounding() -> None:
    assert compute_commission(12_345, 1_000).commission_fcfa == 1_234


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [("floor", 1_234), ("half_up", 1_235), ("ceil", 1_235)],
)
def test_half_franc_follows_the_configured_rule(
    rounding: CommissionRounding, expected: int
) -> None:
    # 12 345 × 10 % = 1 234,5 FCFA : seul cas où les trois règles divergent.
    assert compute_commission(12_345, 1_000, rounding=rounding).commission_fcfa == expected


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [("floor", 1_249), ("half_up", 1_250), ("ceil", 1_250)],
)
def test_fraction_above_half(rounding: CommissionRounding, expected: int) -> None:
    # 9 999 × 12,5 % = 1 249,875 FCFA.
    assert compute_commission(9_999, 1_250, rounding=rounding).commission_fcfa == expected


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [("floor", 1_200), ("half_up", 1_200), ("ceil", 1_201)],
)
def test_fraction_below_half(rounding: CommissionRounding, expected: int) -> None:
    # 12 001 × 10 % = 1 200,1 FCFA.
    assert compute_commission(12_001, 1_000, rounding=rounding).commission_fcfa == expected


@pytest.mark.parametrize("rounding", ROUNDINGS)
def test_commission_plus_net_always_equals_the_amount(rounding: CommissionRounding) -> None:
    # Balayage large : jamais un franc perdu ni créé, jamais de net négatif.
    for amount in (*range(0, 2_001, 7), 99_999, 1_234_567, 2_147_483_647):
        for rate_bps in (0, 1, 333, 999, 1_000, 1_250, 5_000, 9_999, BPS_DENOMINATOR):
            result = compute_commission(amount, rate_bps, rounding=rounding)
            assert result.commission_fcfa + result.net_fcfa == amount
            assert 0 <= result.commission_fcfa <= amount
            assert result.net_fcfa >= 0


def test_results_are_integers_never_floats() -> None:
    result = compute_commission(12_345, 1_000)

    assert type(result.commission_fcfa) is int
    assert type(result.net_fcfa) is int


@pytest.mark.parametrize(
    ("amount", "rate_bps"),
    [
        (-1, 1_000),  # montant négatif
        (1_000, -1),  # taux négatif
        (1_000, BPS_DENOMINATOR + 1),  # taux > 100 %
        (1_000.0, 1_000),  # float refusé, même « rond »
        (1_000, 10.5),
        (True, 1_000),  # bool est un int en Python : refusé explicitement
    ],
)
def test_out_of_domain_inputs_are_refused(amount: object, rate_bps: object) -> None:
    with pytest.raises(ValueError):
        # Entrées volontairement mal typées : on simule une donnée corrompue.
        compute_commission(cast(int, amount), cast(int, rate_bps))
