from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app


async def test_liveness_returns_200() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_200_when_db_reachable() -> None:
    class _WorkingSession:
        async def execute(self, *args: object, **kwargs: object) -> None:
            return None

    async def _working_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield _WorkingSession()  # type: ignore[misc]

    app.dependency_overrides[get_session] = _working_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_503_when_db_unreachable() -> None:
    # La session est mockée ici : on ne veut pas dépendre d'une vraie base
    # injoignable pour tester ce chemin d'erreur.
    class _BrokenSession:
        async def execute(self, *args: object, **kwargs: object) -> None:
            raise SQLAlchemyError("connection refused")

    async def _broken_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield _BrokenSession()  # type: ignore[misc]

    app.dependency_overrides[get_session] = _broken_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert "detail" in body
