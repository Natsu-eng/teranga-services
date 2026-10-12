"""En-têtes de sécurité HTTP sur toutes les réponses (app/core/security_headers.py)."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from httpx import ASGITransport, AsyncClient

from app.core.security_headers import (
    API_CSP,
    BASE_HEADERS,
    DOCS_CSP,
    HSTS,
    SecurityHeadersMiddleware,
)
from app.main import app


def _client(target: FastAPI = app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=target), base_url="http://test")


def _mini_app(*, production: bool, docs_enabled: bool = True) -> FastAPI:
    # Comme app/main.py : sans documentation, aucune route /docs n'existe.
    mini = FastAPI() if docs_enabled else FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @mini.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "oui"}

    @mini.get("/page", response_class=HTMLResponse)
    async def page() -> HTMLResponse:
        # Une route qui fixe sa propre CSP (comme la page sandbox) la garde.
        return HTMLResponse("<p>ok</p>", headers={"Content-Security-Policy": "default-src 'self'"})

    mini.add_middleware(SecurityHeadersMiddleware, production=production, docs_enabled=docs_enabled)
    return mini


async def test_every_api_response_carries_the_security_headers() -> None:
    async with _client() as http:
        ok = await http.get("/api/v1/health")
        not_found = await http.get("/api/v1/nexiste-pas")
        unauthorized = await http.get("/api/v1/admin/overview")

    for response in (ok, not_found, unauthorized):
        for name, value in BASE_HEADERS.items():
            assert response.headers[name] == value
        assert response.headers["Content-Security-Policy"] == API_CSP
        # Hors production : jamais de HSTS (il resterait collé à localhost).
        assert "Strict-Transport-Security" not in response.headers
    assert not_found.status_code == 404
    assert unauthorized.status_code == 401


async def test_hsts_is_sent_in_production_only() -> None:
    async with _client(_mini_app(production=True)) as http:
        prod = await http.get("/ping")
    async with _client(_mini_app(production=False)) as http:
        dev = await http.get("/ping")

    assert prod.headers["Strict-Transport-Security"] == HSTS
    assert "Strict-Transport-Security" not in dev.headers


async def test_a_route_specific_policy_is_never_overridden() -> None:
    async with _client(_mini_app(production=True)) as http:
        response = await http.get("/page")

    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_docs_get_their_relaxed_policy_only_when_enabled() -> None:
    async with _client() as http:
        docs = await http.get("/docs")
    async with _client(_mini_app(production=True, docs_enabled=False)) as http:
        disabled = await http.get("/docs")

    assert docs.status_code == 200
    assert docs.headers["Content-Security-Policy"] == DOCS_CSP
    assert disabled.status_code == 404
    assert disabled.headers["Content-Security-Policy"] == API_CSP


async def test_cors_preflight_also_carries_the_headers() -> None:
    async with _client() as http:
        response = await http.options(
            "/api/v1/health",
            headers={"Origin": "https://inconnu.example", "Access-Control-Request-Method": "GET"},
        )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
