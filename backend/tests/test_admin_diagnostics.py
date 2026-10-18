"""`GET /api/v1/admin/diagnostics/client-ip` : mesurer la chaîne de proxys
pour régler TRUSTED_PROXY_HOPS (DEPLOYMENT.md §12.7)."""

from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from tests.factories import make_user

PATH = "/api/v1/admin/diagnostics/client-ip"
# Chaîne simulée : le client a falsifié l'entrée de gauche, puis deux proxys
# de la plateforme ont chacun ajouté l'adresse qu'ils ont vue.
CHAIN = "6.6.6.6, 203.0.113.7, 10.0.0.2"


@pytest.fixture
def app_with(db_session: AsyncSession) -> Iterator[None]:
    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    yield
    app.dependency_overrides.clear()


def _use_hops(hops: int | None) -> None:
    settings = get_settings().model_copy(update={"trusted_proxy_hops": hops})
    app.dependency_overrides[get_settings] = lambda: settings


async def _get(headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get(PATH, headers=headers)
    return response.status_code, response.json()


@pytest.mark.usefixtures("app_with")
@pytest.mark.parametrize(
    ("hops", "expected"), [(0, "127.0.0.1"), (1, "10.0.0.2"), (2, "203.0.113.7")]
)
async def test_admin_sees_the_raw_chain_and_the_ip_retained_with_current_setting(
    db_session: AsyncSession, hops: int, expected: str
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    _use_hops(hops)

    status, body = await _get(
        {"Authorization": f"Bearer {encode_access_token(admin)}", "X-Forwarded-For": CHAIN}
    )

    assert status == 200
    assert body == {
        "peer": "127.0.0.1",
        "x_forwarded_for": ["6.6.6.6", "203.0.113.7", "10.0.0.2"],
        "trusted_proxy_hops": hops,
        "client_ip": expected,
    }


@pytest.mark.usefixtures("app_with")
async def test_missing_setting_is_reported_as_zero(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    _use_hops(None)

    status, body = await _get({"Authorization": f"Bearer {encode_access_token(admin)}"})

    assert status == 200
    assert body["trusted_proxy_hops"] == 0
    assert body["x_forwarded_for"] == []


@pytest.mark.usefixtures("app_with")
@pytest.mark.parametrize("role", [Role.CLIENT, Role.ARTISAN])
async def test_reserved_to_admins(db_session: AsyncSession, role: Role) -> None:
    user = await make_user(db_session, role=role)

    status, body = await _get({"Authorization": f"Bearer {encode_access_token(user)}"})

    assert status == 403
    assert body["error"]["code"] == "ROLE_INSUFFISANT"


async def test_anonymous_is_refused() -> None:
    status, _ = await _get({"X-Forwarded-For": CHAIN})
    assert status == 401


def test_read_only() -> None:
    assert set(app.openapi()["paths"][PATH]) == {"get"}
