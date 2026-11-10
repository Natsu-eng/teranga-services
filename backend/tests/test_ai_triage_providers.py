"""Tests des fournisseurs de triage IA (app.services.ai_triage_providers).

**Aucun vrai appel réseau à Mistral** : `MistralTriageProvider` est testé en
monkeypatchant `httpx.AsyncClient.post`, qui renvoie de vraies instances
`httpx.Response` (construites en mémoire) -- `raise_for_status()` et
`.json()` se comportent donc exactement comme sur une vraie réponse, sans
dépendance à un mock maison ni à une bibliothèque de mock HTTP additionnelle.
"""

import json
from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.models.enums import Urgency
from app.schemas.ai_triage import TriageResult
from app.services.ai_triage_providers import (
    AiTriageProviderError,
    HeuristicTriageProvider,
    MistralTriageProvider,
    get_ai_triage_provider,
)

# --- HeuristicTriageProvider -------------------------------------------


@pytest.mark.parametrize(
    ("description", "expected_trade_code"),
    [
        ("Le robinet fuit sous l'évier de la cuisine.", "plomberie"),
        ("La prise électrique a disjoncté, plus de courant.", "electricite"),
        ("Le climatiseur ne fait plus du froid du tout.", "climatisation"),
        ("La serrure de la porte en bois est cassée.", "menuiserie"),
        ("Une fissure dans le mur en béton du salon.", "maconnerie"),
        ("Mon WC est bouché depuis hier.", "plomberie"),
    ],
)
async def test_heuristic_detects_trade_code_from_french_keywords(
    description: str, expected_trade_code: str
) -> None:
    result = await HeuristicTriageProvider().analyze(description)
    assert result.trade_code == expected_trade_code


@pytest.mark.parametrize(
    "description",
    [
        "Mon problème n'a aucun mot-clé reconnu.",
        "J'ai besoin d'un jardinier pour la haie.",
        # Mots qui CONTIENNENT un ancien mot-clé trop court (« eau », « bouch »).
        "Mon bureau est tout nouveau.",
        "Le boucher du quartier est fermé.",
    ],
)
async def test_heuristic_never_invents_a_trade_nor_amounts(description: str) -> None:
    """Aucun mot-clé reconnu : plus de « plomberie » par défaut présentée
    comme détectée, et aucun montant (rien ne serait fondé)."""
    result = await HeuristicTriageProvider().analyze(description)
    assert result.trade_code is None
    assert (result.price_min_fcfa, result.price_max_fcfa, result.suggested_quote) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "trade_code", ["plomberie", "electricite", "climatisation", "menuiserie", "maconnerie"]
)
async def test_heuristic_returns_a_schema_valid_result_for_every_known_trade(
    trade_code: str,
) -> None:
    descriptions = {
        "plomberie": "fuite d'eau",
        "electricite": "prise électrique en panne",
        "climatisation": "clim en panne",
        "menuiserie": "porte en bois cassée",
        "maconnerie": "fissure dans le mur",
    }
    result = await HeuristicTriageProvider().analyze(descriptions[trade_code])

    assert isinstance(result, TriageResult)
    assert result.trade_code == trade_code
    assert result.price_min_fcfa is not None and result.price_max_fcfa is not None
    assert result.suggested_quote is not None
    assert result.price_min_fcfa <= result.price_max_fcfa
    assert result.suggested_quote.total_fcfa == (
        result.suggested_quote.labor_fcfa + result.suggested_quote.materials_fcfa
    )


async def test_heuristic_detects_immediate_urgency() -> None:
    result = await HeuristicTriageProvider().analyze(
        "Fuite d'eau, il faut intervenir immédiatement."
    )
    assert result.urgency is Urgency.IMMEDIAT


async def test_heuristic_detects_urgent_keyword() -> None:
    result = await HeuristicTriageProvider().analyze("C'est urgent, ça inonde la cuisine.")
    assert result.urgency is Urgency.URGENT


async def test_heuristic_defaults_to_normal_urgency() -> None:
    result = await HeuristicTriageProvider().analyze(
        "Le robinet goutte un peu depuis quelques jours."
    )
    assert result.urgency is Urgency.NORMAL


# --- MistralTriageProvider ----------------------------------------------


def _settings(**overrides: object) -> Settings:
    base = get_settings().model_copy(
        update={
            "mistral_api_key": "test-key",
            "mistral_model": "mistral-small-latest",
            "mistral_api_base_url": "https://api.mistral.test/v1",
            "mistral_timeout_seconds": 5.0,
            **overrides,
        }
    )
    return base


def _mistral_response(status_code: int, json_body: object) -> httpx.Response:
    request = httpx.Request("POST", "https://api.mistral.test/v1/chat/completions")
    return httpx.Response(status_code, json=json_body, request=request)


def _chat_completion(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"content": content}}]}


def _valid_content() -> str:
    return json.dumps(
        {
            "trade_code": "plomberie",
            "price_min_fcfa": 8_000,
            "price_max_fcfa": 15_000,
            "urgency": "normal",
            "suggested_quote": {"labor_fcfa": 8_000, "materials_fcfa": 4_000, "total_fcfa": 12_000},
        }
    )


def _patch_post(monkeypatch: pytest.MonkeyPatch, handler: Callable[..., httpx.Response]) -> None:
    async def _fake_post(
        self: httpx.AsyncClient, *args: object, **kwargs: object
    ) -> httpx.Response:
        return handler(*args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)


async def test_mistral_returns_a_validated_triage_result_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(
        monkeypatch,
        lambda *a, **k: _mistral_response(200, _chat_completion(_valid_content())),
    )

    result = await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")

    assert result.trade_code == "plomberie"
    assert result.suggested_quote is not None
    assert result.suggested_quote.total_fcfa == 12_000


async def test_mistral_raises_provider_error_without_calling_network_when_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_post(
        self: httpx.AsyncClient, *args: object, **kwargs: object
    ) -> httpx.Response:
        nonlocal called
        called = True
        return _mistral_response(200, _chat_completion(_valid_content()))

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings(mistral_api_key=None)).analyze("Le robinet fuit.")

    assert called is False


async def test_mistral_raises_provider_error_on_malformed_json_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(
        monkeypatch,
        lambda *a, **k: _mistral_response(200, _chat_completion("pas du json valide {")),
    )

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")


async def test_mistral_raises_provider_error_when_trade_code_field_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incomplete = json.dumps({"price_min_fcfa": 8_000, "price_max_fcfa": 15_000})
    _patch_post(monkeypatch, lambda *a, **k: _mistral_response(200, _chat_completion(incomplete)))

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")


async def test_mistral_raises_provider_error_on_inconsistent_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inconsistent = json.dumps(
        {
            "trade_code": "plomberie",
            "price_min_fcfa": 8_000,
            "price_max_fcfa": 15_000,
            "urgency": "normal",
            "suggested_quote": {
                "labor_fcfa": 8_000,
                "materials_fcfa": 4_000,
                "total_fcfa": 999_999,
            },
        }
    )
    _patch_post(monkeypatch, lambda *a, **k: _mistral_response(200, _chat_completion(inconsistent)))

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")


async def test_mistral_raises_provider_error_on_http_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(monkeypatch, lambda *a, **k: _mistral_response(500, {"error": "boom"}))

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")


async def test_mistral_raises_provider_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_post(
        self: httpx.AsyncClient, *args: object, **kwargs: object
    ) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    with pytest.raises(AiTriageProviderError):
        await MistralTriageProvider(_settings()).analyze("Le robinet fuit.")


# --- get_ai_triage_provider (sélection par Settings) ---------------------


def test_get_ai_triage_provider_defaults_to_heuristic() -> None:
    provider = get_ai_triage_provider(_settings(ai_triage_provider="heuristic"))
    assert isinstance(provider, HeuristicTriageProvider)


def test_get_ai_triage_provider_returns_mistral_when_configured() -> None:
    provider = get_ai_triage_provider(_settings(ai_triage_provider="mistral"))
    assert isinstance(provider, MistralTriageProvider)
