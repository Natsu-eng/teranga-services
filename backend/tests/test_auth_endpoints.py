"""Tests d'intégration bout-en-bout des endpoints /api/v1/auth.

`get_session` est substitué par la session transactionnelle du test
(`db_session`, cf. conftest.py) : les endpoints appellent `session.commit()`
comme en production, mais grâce au mode savepoint de la fixture, tout est
annulé à la fin du test. `get_otp_rate_limiter` est substitué par une
instance fraîche à chaque test pour ne pas partager de compteurs entre tests
(le singleton de production est un état par-processus).
"""

import logging
import re
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.refresh_token import RefreshToken
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter
from tests.factories import unique_phone

_OTP_LOG_PATTERN = re.compile(r"Code OTP pour \S+ : (\d+)")


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Une seule instance, réutilisée pour toutes les requêtes du test : le
    # rate limiter doit accumuler ses hits sur plusieurs appels HTTP,
    # contrairement à une factory qui en recréerait une neuve à chaque
    # résolution de dépendance (une par requête).
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_otp_rate_limiter] = lambda: fresh_rate_limiter


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_otp_rate_limiter, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _extract_otp_code(caplog_text: str) -> str:
    match = _OTP_LOG_PATTERN.search(caplog_text)
    assert match is not None, f"code OTP introuvable dans les logs : {caplog_text!r}"
    return match.group(1)


async def _request_and_capture_code(
    client: AsyncClient, phone: str, caplog: pytest.LogCaptureFixture
) -> str:
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = await client.post("/api/v1/auth/request-otp", json={"phone": phone})
    assert response.status_code == 204
    return _extract_otp_code(caplog.text)


async def test_request_otp_always_returns_204(caplog: pytest.LogCaptureFixture) -> None:
    async with await _client() as client:
        # Numéro sans compte existant.
        response = await client.post("/api/v1/auth/request-otp", json={"phone": unique_phone()})
        assert response.status_code == 204
        assert response.text == ""


async def test_request_otp_rejects_invalid_phone_with_normalized_error() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/auth/request-otp", json={"phone": "pas-un-numero"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "TELEPHONE_INVALIDE"
    assert isinstance(body["error"]["message"], str)


async def test_verify_otp_wrong_code_returns_normalized_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        await _request_and_capture_code(client, phone, caplog)

        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": "000000", "intent": "login"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALIDE"


async def test_full_nominal_cycle_creates_account_and_issues_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)

        verify_response = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": phone,
                "code": code,
                "intent": "signup",
                "role": "client",
                "full_name": "Fatou Sarr",
            },
        )
        assert verify_response.status_code == 200
        body = verify_response.json()
        assert body["user"]["phone"] == phone
        assert body["user"]["role"] == "client"
        assert body["user"]["phone_verified_at"] is not None
        access = body["access"]
        refresh = body["refresh"]

        # GET /me avec l'access token émis.
        me_response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["phone"] == phone

        # /refresh : rotation -- nouveau couple, l'ancien refresh est mort.
        refresh_response = await client.post("/api/v1/auth/refresh", json={"refresh": refresh})
        assert refresh_response.status_code == 200
        new_refresh = refresh_response.json()["refresh"]
        assert new_refresh != refresh

        replay_response = await client.post("/api/v1/auth/refresh", json={"refresh": refresh})
        assert replay_response.status_code == 401
        assert replay_response.json()["error"]["code"] == "REFRESH_REUTILISE"

        # La famille entière (y compris new_refresh, issu de la rotation
        # légitime) est révoquée par le signal de vol ci-dessus.
        family_response = await client.post("/api/v1/auth/refresh", json={"refresh": new_refresh})
        assert family_response.status_code == 401


async def test_verify_otp_reuses_existing_account_on_second_login(
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code_1 = await _request_and_capture_code(client, phone, caplog)
        first = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": phone,
                "code": code_1,
                "intent": "signup",
                "role": "client",
                "full_name": "Fatou Sarr",
            },
        )
        user_id_first = first.json()["user"]["id"]

        code_2 = await _request_and_capture_code(client, phone, caplog)
        second = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": code_2, "intent": "login"},
        )
        user_id_second = second.json()["user"]["id"]

    assert user_id_first == user_id_second


async def test_logout_revokes_the_refresh_token(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        verify_response = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": phone,
                "code": code,
                "intent": "signup",
                "role": "client",
                "full_name": "Fatou Sarr",
            },
        )
        refresh = verify_response.json()["refresh"]

        logout_response = await client.post("/api/v1/auth/logout", json={"refresh": refresh})
        assert logout_response.status_code == 204

        reuse_response = await client.post("/api/v1/auth/refresh", json={"refresh": refresh})
        assert reuse_response.status_code == 401


async def test_logout_all_revokes_every_session(caplog: pytest.LogCaptureFixture) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code_1 = await _request_and_capture_code(client, phone, caplog)
        session_1 = (
            await client.post(
                "/api/v1/auth/verify-otp",
                json={
                    "phone": phone,
                    "code": code_1,
                    "intent": "signup",
                    "role": "client",
                    "full_name": "Fatou Sarr",
                },
            )
        ).json()

        code_2 = await _request_and_capture_code(client, phone, caplog)
        session_2 = (
            await client.post(
                "/api/v1/auth/verify-otp",
                json={"phone": phone, "code": code_2, "intent": "login"},
            )
        ).json()

        logout_all_response = await client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {session_1['access']}"},
        )
        assert logout_all_response.status_code == 204

        for refresh in (session_1["refresh"], session_2["refresh"]):
            response = await client.post("/api/v1/auth/refresh", json={"refresh": refresh})
            assert response.status_code == 401


async def test_me_requires_authentication() -> None:
    async with await _client() as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NON_AUTHENTIFIE"


async def test_me_rejects_garbage_bearer_token() -> None:
    async with await _client() as client:
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer pas-un-jwt"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALIDE"


async def test_request_otp_rate_limited_by_phone(caplog: pytest.LogCaptureFixture) -> None:
    phone = unique_phone()
    settings = get_settings()
    async with await _client() as client:
        for _ in range(settings.rate_limit_otp_per_phone_max):
            response = await client.post("/api/v1/auth/request-otp", json={"phone": phone})
            assert response.status_code == 204

        limited_response = await client.post("/api/v1/auth/request-otp", json={"phone": phone})

    assert limited_response.status_code == 429
    assert limited_response.json()["error"]["code"] == "TROP_DE_DEMANDES"


async def test_request_otp_rate_limited_by_ip_across_different_phones() -> None:
    settings = get_settings()
    async with await _client() as client:
        for _ in range(settings.rate_limit_otp_per_ip_max):
            response = await client.post("/api/v1/auth/request-otp", json={"phone": unique_phone()})
            assert response.status_code == 204

        limited_response = await client.post(
            "/api/v1/auth/request-otp", json={"phone": unique_phone()}
        )

    assert limited_response.status_code == 429
    assert limited_response.json()["error"]["code"] == "TROP_DE_DEMANDES"


async def test_verify_otp_persists_hashed_refresh_token(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": phone,
                "code": code,
                "intent": "signup",
                "role": "client",
                "full_name": "Fatou Sarr",
            },
        )
    refresh = response.json()["refresh"]

    rows = (await db_session.execute(select(RefreshToken))).scalars().all()
    assert all(refresh not in row.token_hash for row in rows)


async def test_new_account_created_via_otp_has_client_role(
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": phone,
                "code": code,
                "intent": "signup",
                "role": "client",
                "full_name": "Fatou Sarr",
            },
        )

    assert response.json()["user"]["role"] == Role.CLIENT.value
