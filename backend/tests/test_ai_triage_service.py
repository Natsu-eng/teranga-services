"""Tests de l'orchestrateur de triage IA (app.services.ai_triage.analyze_problem) :
sélection du fournisseur, validation post-réponse (existence du trade_code
en base), fallback heuristique systématique en cas d'anomalie -- jamais
d'exception propagée au client (BUILD_PLAN.md §6 Lot 11)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.enums import Urgency
from app.schemas.ai_triage import SuggestedQuoteOut, TriageResult
from app.services import ai_triage
from app.services.ai_triage_providers import AiTriageProviderError
from tests.factories import make_trade


def _fake_result(trade_code: str = "plomberie") -> TriageResult:
    return TriageResult(
        trade_code=trade_code,
        price_min_fcfa=8_000,
        price_max_fcfa=15_000,
        urgency=Urgency.NORMAL,
        suggested_quote=SuggestedQuoteOut(
            labor_fcfa=8_000, materials_fcfa=4_000, total_fcfa=12_000
        ),
    )


class _FakeProvider:
    def __init__(self, result: TriageResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def analyze(self, description: str) -> TriageResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _mistral_settings() -> Settings:
    return get_settings().model_copy(update={"ai_triage_provider": "mistral"})


async def test_heuristic_provider_never_touches_the_database(db_session: AsyncSession) -> None:
    settings = get_settings().model_copy(update={"ai_triage_provider": "heuristic"})

    result = await ai_triage.analyze_problem(db_session, "Le robinet fuit.", settings=settings)

    assert result.trade_code == "plomberie"


async def test_provider_result_is_returned_unchanged_when_trade_code_exists(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trade = await make_trade(db_session, code="plomberie")
    fake = _FakeProvider(result=_fake_result(trade_code=trade.code))
    monkeypatch.setattr(ai_triage, "get_ai_triage_provider", lambda settings: fake)

    result = await ai_triage.analyze_problem(
        db_session, "Le robinet fuit.", settings=_mistral_settings()
    )

    assert result.trade_code == trade.code


async def test_falls_back_to_heuristic_when_trade_code_does_not_exist(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeProvider(result=_fake_result(trade_code="code-totalement-inexistant"))
    monkeypatch.setattr(ai_triage, "get_ai_triage_provider", lambda settings: fake)

    result = await ai_triage.analyze_problem(
        db_session, "Le robinet fuit.", settings=_mistral_settings()
    )

    # Rejet + fallback, jamais un mapping approximatif vers un métier proche.
    assert result.trade_code != "code-totalement-inexistant"
    assert result.trade_code == "plomberie"


async def test_falls_back_to_heuristic_when_trade_code_exists_but_is_inactive(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trade = await make_trade(db_session, code="plomberie")
    trade.is_active = False
    await db_session.flush()
    fake = _FakeProvider(result=_fake_result(trade_code=trade.code))
    monkeypatch.setattr(ai_triage, "get_ai_triage_provider", lambda settings: fake)

    result = await ai_triage.analyze_problem(
        db_session, "Le robinet fuit.", settings=_mistral_settings()
    )

    assert result.trade_code != trade.code


async def test_falls_back_to_heuristic_when_provider_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeProvider(error=AiTriageProviderError("timeout"))
    monkeypatch.setattr(ai_triage, "get_ai_triage_provider", lambda settings: fake)

    result = await ai_triage.analyze_problem(
        db_session, "La prise électrique ne fonctionne plus.", settings=_mistral_settings()
    )

    assert isinstance(result, TriageResult)
    assert result.trade_code == "electricite"


async def test_a_provider_without_trade_is_relayed_without_a_default_trade(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le fournisseur ne reconnaît aucun métier : la réponse le dit telle
    quelle -- pas de repli heuristique qui imposerait un métier."""
    no_trade = TriageResult(trade_code=None, urgency=Urgency.NORMAL)
    monkeypatch.setattr(
        ai_triage, "get_ai_triage_provider", lambda settings: _FakeProvider(result=no_trade)
    )

    result = await ai_triage.analyze_problem(
        db_session, "Une demande hors des métiers proposés.", settings=_mistral_settings()
    )

    assert result == no_trade


async def test_output_contract_is_stable_across_providers(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le client reçoit toujours la même forme de TriageResult, que la
    réponse vienne du fournisseur réseau ou du fallback heuristique."""
    trade = await make_trade(db_session, code="plomberie")
    fake = _FakeProvider(result=_fake_result(trade_code=trade.code))
    monkeypatch.setattr(ai_triage, "get_ai_triage_provider", lambda settings: fake)
    from_provider = await ai_triage.analyze_problem(
        db_session, "Le robinet fuit.", settings=_mistral_settings()
    )

    heuristic_settings = get_settings().model_copy(update={"ai_triage_provider": "heuristic"})
    from_heuristic = await ai_triage.analyze_problem(
        db_session, "Le robinet fuit.", settings=heuristic_settings
    )

    assert set(from_provider.model_dump()) == set(from_heuristic.model_dump())
    assert from_provider.suggested_quote is not None
    assert from_heuristic.suggested_quote is not None
    assert set(from_provider.suggested_quote.model_dump()) == set(
        from_heuristic.suggested_quote.model_dump()
    )
