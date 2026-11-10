"""Validation stricte de la sortie IA (app.schemas.ai_triage) -- le
durcissement pointé par l'audit du Lot 0 sur l'ancien endpoint Express, qui
ne validait rien (regex + parse sans contrôle)."""

import pytest
from pydantic import ValidationError

from app.models.enums import Urgency
from app.schemas.ai_triage import SuggestedQuoteOut, TriageResult


def _quote(labor: int = 8_000, materials: int = 4_000, total: int | None = None) -> dict[str, int]:
    return {
        "labor_fcfa": labor,
        "materials_fcfa": materials,
        "total_fcfa": total if total is not None else labor + materials,
    }


def test_accepts_no_trade_without_any_amount() -> None:
    result = TriageResult(trade_code=None, urgency=Urgency.NORMAL)
    assert result.price_min_fcfa is None and result.suggested_quote is None


@pytest.mark.parametrize(
    "amounts",
    [
        {"price_min_fcfa": 8_000},
        {"price_max_fcfa": 15_000},
        {"suggested_quote": _quote()},
    ],
)
def test_rejects_an_amount_without_a_trade(amounts: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="Aucun montant sans métier"):
        TriageResult.model_validate({"trade_code": None, "urgency": "normal", **amounts})


@pytest.mark.parametrize("missing", ["price_min_fcfa", "price_max_fcfa", "suggested_quote"])
def test_rejects_a_trade_without_its_amounts(missing: str) -> None:
    payload: dict[str, object] = {
        "trade_code": "plomberie",
        "price_min_fcfa": 8_000,
        "price_max_fcfa": 15_000,
        "urgency": "normal",
        "suggested_quote": _quote(),
    }
    del payload[missing]
    with pytest.raises(ValidationError, match="requis avec un métier"):
        TriageResult.model_validate(payload)


def test_accepts_a_consistent_result() -> None:
    result = TriageResult(
        trade_code="plomberie",
        price_min_fcfa=8_000,
        price_max_fcfa=15_000,
        urgency=Urgency.NORMAL,
        suggested_quote=SuggestedQuoteOut(**_quote()),
    )
    assert result.suggested_quote is not None
    assert result.suggested_quote.total_fcfa == 12_000


def test_rejects_quote_whose_total_does_not_match_labor_plus_materials() -> None:
    with pytest.raises(ValidationError, match="total_fcfa"):
        SuggestedQuoteOut(**_quote(labor=8_000, materials=4_000, total=999_999))


def test_rejects_negative_labor_amount() -> None:
    with pytest.raises(ValidationError):
        SuggestedQuoteOut(**_quote(labor=-1))


def test_rejects_price_max_below_price_min() -> None:
    with pytest.raises(ValidationError, match="price_max_fcfa"):
        TriageResult(
            trade_code="plomberie",
            price_min_fcfa=20_000,
            price_max_fcfa=10_000,
            urgency=Urgency.NORMAL,
            suggested_quote=SuggestedQuoteOut(**_quote()),
        )


def test_rejects_negative_price() -> None:
    with pytest.raises(ValidationError):
        TriageResult(
            trade_code="plomberie",
            price_min_fcfa=-1,
            price_max_fcfa=10_000,
            urgency=Urgency.NORMAL,
            suggested_quote=SuggestedQuoteOut(**_quote()),
        )


def test_rejects_urgency_outside_the_closed_enum() -> None:
    with pytest.raises(ValidationError):
        TriageResult(
            trade_code="plomberie",
            price_min_fcfa=8_000,
            price_max_fcfa=15_000,
            urgency="haute",
            suggested_quote=SuggestedQuoteOut(**_quote()),
        )
