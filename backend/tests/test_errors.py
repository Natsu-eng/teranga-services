"""Vérifie le format d'erreur normalisé (BUILD_PLAN.md §3.1) indépendamment
de l'app principale : une petite app FastAPI jetable, câblée avec les mêmes
gestionnaires, isole ce test de toute dépendance métier (auth, DB…).
"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, register_exception_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-app-error")
    async def _boom_app_error() -> None:
        raise AppError(code="TEST_ERROR", message="Erreur de test.", status_code=418)

    @app.get("/boom-http-exception")
    async def _boom_http_exception() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Introuvable.")

    @app.post("/boom-validation")
    async def _boom_validation(payload: dict[str, int]) -> dict[str, int]:
        return payload

    return app


async def test_app_error_returns_normalized_json() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom-app-error")

    assert response.status_code == 418
    assert response.json() == {"error": {"code": "TEST_ERROR", "message": "Erreur de test."}}


async def test_http_exception_returns_normalized_json() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom-http-exception")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["error"]["message"] == "Introuvable."


async def test_validation_error_returns_normalized_json() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/boom-validation", content=b"not json")

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "VALIDATION_ERROR", "message": "Requête invalide."}
    }
