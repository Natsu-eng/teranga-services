"""`GET /api/v1/meta` : environnement et mode OTP de test, sans aucun secret."""

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import app

TEST_CODE = "482913"
TEST_NUMBER = "+221770000001"


@pytest.fixture
def with_settings() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_settings, None)


async def _meta(settings: Settings) -> dict[str, object]:
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/v1/meta")
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


@pytest.mark.usefixtures("with_settings")
async def test_staging_with_test_mode_reports_it_without_any_secret() -> None:
    settings = get_settings().model_copy(
        update={
            "environment": "staging",
            "otp_test_whitelist": [TEST_NUMBER],
            "otp_test_code": TEST_CODE,
        }
    )

    body = await _meta(settings)

    assert body == {"environment": "staging", "otp_test_mode": True}
    # Ni le numéro ni le code, sous aucune forme.
    raw = str(body)
    assert TEST_NUMBER not in raw
    assert TEST_CODE not in raw


@pytest.mark.usefixtures("with_settings")
@pytest.mark.parametrize("environment", ["development", "test", "staging"])
async def test_non_production_without_test_mode(environment: str) -> None:
    settings = get_settings().model_copy(update={"environment": environment})
    assert await _meta(settings) == {"environment": environment, "otp_test_mode": False}


@pytest.mark.usefixtures("with_settings")
async def test_production_reports_production_and_never_the_test_mode() -> None:
    # Même une configuration de test forcée (validation contournée) n'apparaît
    # pas en production : le mode n'y existe pas (verrou d'exécution).
    settings = get_settings().model_copy(
        update={
            "environment": "production",
            "otp_test_whitelist": [TEST_NUMBER],
            "otp_test_code": TEST_CODE,
        }
    )
    assert await _meta(settings) == {"environment": "production", "otp_test_mode": False}


async def test_meta_is_public() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/v1/meta")
    assert response.status_code == 200
    assert set(response.json()) == {"environment", "otp_test_mode"}
