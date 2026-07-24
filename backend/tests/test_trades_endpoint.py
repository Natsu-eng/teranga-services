"""Test d'intégration de GET /api/v1/trades (référentiel des métiers)."""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.trade import Trade


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_list_trades_returns_active_trades_ordered_by_sort_order(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Trade(code="menuiserie-t", label_fr="Menuiserie", sort_order=2, is_active=True),
            Trade(code="plomberie-t", label_fr="Plomberie", sort_order=1, is_active=True),
            Trade(code="obsolete-t", label_fr="Obsolète", sort_order=0, is_active=False),
        ]
    )
    await db_session.flush()

    async with await _client() as client:
        response = await client.get("/api/v1/trades")

    assert response.status_code == 200
    codes = [t["code"] for t in response.json()]
    assert "obsolete-t" not in codes
    assert codes.index("plomberie-t") < codes.index("menuiserie-t")


async def test_list_trades_response_shape(db_session: AsyncSession) -> None:
    db_session.add(
        Trade(
            code="electricite-t",
            label_fr="Électricité",
            label_wo=None,
            icon="bolt",
            sort_order=1,
            is_active=True,
        )
    )
    await db_session.flush()

    async with await _client() as client:
        response = await client.get("/api/v1/trades")

    body = response.json()
    item = next(t for t in body if t["code"] == "electricite-t")
    assert item["label_fr"] == "Électricité"
    assert item["icon"] == "bolt"
    assert item["label_wo"] is None
