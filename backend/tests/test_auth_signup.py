"""Distinction inscription/connexion sur `POST /auth/verify-otp` (BUILD_PLAN.md
§4) : `intent`/`role` explicites, `admin` jamais attribuable, un compte
existant ne change jamais de rôle. `request-otp` reste hors-scope de ces
tests (inchangé, déjà couvert par `test_auth_endpoints.py`).
"""

import logging
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role
from app.models.user import User
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter
from tests.factories import unique_phone
from tests.test_auth_endpoints import _extract_otp_code


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

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


async def _request_and_capture_code(
    client: AsyncClient, phone: str, caplog: pytest.LogCaptureFixture
) -> str:
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = await client.post("/api/v1/auth/request-otp", json={"phone": phone})
    assert response.status_code == 204
    return _extract_otp_code(caplog.text)


async def _verify(
    client: AsyncClient,
    phone: str,
    code: str,
    *,
    intent: str,
    role: str | None = None,
    full_name: str | None = "Fatou Sarr",
) -> Response:
    payload: dict[str, str] = {"phone": phone, "code": code, "intent": intent}
    if role is not None:
        payload["role"] = role
    if full_name is not None:
        payload["full_name"] = full_name
    return await client.post("/api/v1/auth/verify-otp", json=payload)


async def test_signup_client_creates_account_with_no_artisan_profile(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(
            client, phone, code, intent="signup", role="client", full_name="Fatou Sarr"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "client"
    assert body["user"]["artisan_profile_id"] is None
    # Fix confidentialité du contact (BUILD_PLAN.md) : le nom est celui
    # fourni, jamais le placeholder historique = le numéro de téléphone.
    assert body["user"]["full_name"] == "Fatou Sarr"
    assert body["user"]["full_name"] != phone


async def test_signup_artisan_creates_empty_unavailable_profile(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(client, phone, code, intent="signup", role="artisan")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "artisan"
    profile_id = body["user"]["artisan_profile_id"]
    assert profile_id is not None

    profile = await db_session.get(ArtisanProfile, profile_id)
    assert profile is not None
    assert profile.is_available is False
    assert profile.verified_status.value == "none"


async def test_signup_rejects_admin_role(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(client, phone, code, intent="signup", role="admin")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_without_a_role_is_rejected(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    # `role` est optionnel dans le schéma (`None` par défaut, pertinent
    # uniquement pour un login) -- pydantic seul ne peut pas exiger "requis
    # si intent == signup" (validation croisée entre champs). C'est le
    # chemin réellement atteint par l'allow-list explicite du service
    # (`RoleInscriptionInvalideError`), contrairement à `role="admin"`/
    # `"superadmin"` déjà bloqués plus tôt par le typage `Literal` du schéma.
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(client, phone, code, intent="signup")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROLE_INSCRIPTION_INVALIDE"

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_rejects_unknown_role_value(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": code, "intent": "signup", "role": "superadmin"},
        )

    assert response.status_code == 422

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_rejects_already_existing_phone_without_changing_role(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code_1 = await _request_and_capture_code(client, phone, caplog)
        first = await _verify(client, phone, code_1, intent="signup", role="client")
        assert first.status_code == 200
        user_id = first.json()["user"]["id"]

        code_2 = await _request_and_capture_code(client, phone, caplog)
        second = await _verify(client, phone, code_2, intent="signup", role="artisan")

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "COMPTE_DEJA_EXISTANT"

    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.role == Role.CLIENT  # jamais écrasé par la seconde tentative


async def test_login_rejects_nonexistent_phone_without_creating_an_account(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(client, phone, code, intent="login")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COMPTE_INEXISTANT"

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_without_a_name_is_rejected(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(
            client, phone, code, intent="signup", role="client", full_name=None
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOM_INVALIDE"

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_with_a_blank_name_is_rejected(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(
            client, phone, code, intent="signup", role="artisan", full_name="   "
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOM_INVALIDE"

    created = (
        await db_session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    assert created is None


async def test_signup_name_is_trimmed(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code = await _request_and_capture_code(client, phone, caplog)
        response = await _verify(
            client, phone, code, intent="signup", role="client", full_name="  Fatou Sarr  "
        )

    assert response.status_code == 200
    assert response.json()["user"]["full_name"] == "Fatou Sarr"


async def test_login_does_not_change_the_existing_name(
    caplog: pytest.LogCaptureFixture, db_session: AsyncSession
) -> None:
    """Un `full_name` envoyé sur une requête `login` est ignoré -- le nom
    d'un compte existant ne change jamais via ce flux (édition dédiée,
    `PATCH /artisans/me` ou `PATCH /users/me`)."""
    phone = unique_phone()
    async with await _client() as client:
        code_1 = await _request_and_capture_code(client, phone, caplog)
        signup = await _verify(
            client, phone, code_1, intent="signup", role="client", full_name="Fatou Sarr"
        )
        assert signup.status_code == 200

        code_2 = await _request_and_capture_code(client, phone, caplog)
        login = await _verify(
            client, phone, code_2, intent="login", role=None, full_name="Nom Different"
        )

    assert login.status_code == 200
    assert login.json()["user"]["full_name"] == "Fatou Sarr"


async def test_login_nominal_reuses_the_existing_account(
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = unique_phone()
    async with await _client() as client:
        code_1 = await _request_and_capture_code(client, phone, caplog)
        signup = await _verify(client, phone, code_1, intent="signup", role="artisan")
        assert signup.status_code == 200
        user_id_signup = signup.json()["user"]["id"]

        code_2 = await _request_and_capture_code(client, phone, caplog)
        login = await _verify(client, phone, code_2, intent="login")

    assert login.status_code == 200
    body = login.json()
    assert body["user"]["id"] == user_id_signup
    assert body["user"]["role"] == "artisan"
