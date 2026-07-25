"""Tests d'intégration bout-en-bout de `POST /api/v1/ai/analyze`
(BUILD_PLAN.md §3.2, §6 Lot 11).

Le fournisseur par défaut (`AI_TRIAGE_PROVIDER=heuristic`, voir
backend/.env.example) est utilisé tel quel -- ces tests ne font jamais
d'appel réseau réel à Mistral (couverture dédiée, entièrement mockée :
tests/test_ai_triage_providers.py). `get_ai_analyze_rate_limiter` est
substitué par une instance fraîche à chaque test, même raison que
test_auth_endpoints.py (le singleton de production est un état
par-processus, partagé entre tests sinon).
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.services.rate_limit import SlidingWindowRateLimiter, get_ai_analyze_rate_limiter


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_ai_analyze_rate_limiter] = lambda: fresh_rate_limiter


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_ai_analyze_rate_limiter, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_analyze_returns_a_valid_triage_result_for_a_plumbing_description() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/ai/analyze",
            json={"description": "Le robinet de la cuisine fuit sous l'évier."},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["trade_code"] == "plomberie"
    assert body["price_min_fcfa"] <= body["price_max_fcfa"]
    quote = body["suggested_quote"]
    assert quote["total_fcfa"] == quote["labor_fcfa"] + quote["materials_fcfa"]


async def test_analyze_response_contract_has_exactly_the_expected_keys() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/ai/analyze", json={"description": "Une prise électrique ne fonctionne plus."}
        )

    body = response.json()
    assert set(body) == {
        "trade_code",
        "price_min_fcfa",
        "price_max_fcfa",
        "urgency",
        "suggested_quote",
    }
    assert set(body["suggested_quote"]) == {"labor_fcfa", "materials_fcfa", "total_fcfa"}


async def test_analyze_does_not_require_authentication() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/ai/analyze", json={"description": "Le climatiseur ne refroidit plus."}
        )

    assert response.status_code == 200


async def test_analyze_rejects_a_too_short_description() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/ai/analyze", json={"description": "a"})

    assert response.status_code == 422


async def test_analyze_rejects_a_missing_description() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/ai/analyze", json={})

    assert response.status_code == 422


async def test_analyze_is_rate_limited_by_ip() -> None:
    settings = get_settings()
    async with await _client() as client:
        for _ in range(settings.rate_limit_ai_analyze_per_ip_max):
            response = await client.post(
                "/api/v1/ai/analyze",
                json={"description": "Une prise électrique ne fonctionne plus."},
            )
            assert response.status_code == 200

        limited_response = await client.post(
            "/api/v1/ai/analyze",
            json={"description": "Une prise électrique ne fonctionne plus."},
        )

    assert limited_response.status_code == 429
    assert limited_response.json()["error"]["code"] == "TROP_DE_DEMANDES"
