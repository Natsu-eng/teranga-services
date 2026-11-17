"""Abonnements des appareils aux notifications push (`/api/v1/push`).

Application réelle en ASGI, base de dev dans une transaction annulée.
Aucune clé en dur : paire VAPID et clés « navigateur » générées par test.
"""

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.core.vapid import b64url_encode, encode_public_key, generate_key_pair
from app.db.session import get_session
from app.main import app
from app.models.enums import Role
from app.models.push import PushSubscription
from app.models.user import User
from app.services.rate_limit import SlidingWindowRateLimiter, get_push_subscription_rate_limiter
from tests.factories import make_user

FCM = "https://fcm.googleapis.com/fcm/send/"


def browser_keys() -> dict[str, str]:
    """Clés d'un navigateur abonné : point P-256 réel + secret de 16 octets."""
    from cryptography.hazmat.primitives.asymmetric import ec

    public = ec.generate_private_key(ec.SECP256R1()).public_key()
    return {"p256dh": encode_public_key(public), "auth": b64url_encode(os.urandom(16))}


def subscription(endpoint: str | None = None, **keys: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint or f"{FCM}{uuid.uuid4().hex}",
        "expirationTime": None,  # envoyé par le navigateur, ignoré
        "keys": {**browser_keys(), **keys},
    }


@pytest.fixture(autouse=True)
def _app(db_session: AsyncSession) -> Generator[None, None, None]:
    public_key, private_key = generate_key_pair()
    settings = get_settings().model_copy(
        update={
            "web_push_enabled": True,
            "vapid_public_key": public_key,
            "vapid_private_key": private_key,
            "vapid_subject": "mailto:contact@teranga.example",
            "web_push_max_subscriptions_per_user": 3,
        }
    )

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_push_subscription_rate_limiter] = lambda: limiter
    yield
    app.dependency_overrides.clear()


def _override_settings(**changes: Any) -> None:
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(update=changes)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _rows(session: AsyncSession, user: User) -> list[PushSubscription]:
    result = await session.execute(
        select(PushSubscription)
        .where(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.updated_at)
    )
    return list(result.scalars().all())


async def _subscribe(client: AsyncClient, user: User, body: dict[str, Any]) -> int:
    response = await client.post("/api/v1/push/subscriptions", json=body, headers=_auth(user))
    return response.status_code


# ------------------------------------------------------------ configuration


async def test_config_gives_the_public_key_when_enabled(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        response = await client.get("/api/v1/push/config", headers=_auth(user))
    settings = app.dependency_overrides[get_settings]()
    assert response.json() == {"enabled": True, "vapid_public_key": settings.vapid_public_key}
    assert settings.vapid_private_key not in response.text


async def test_config_says_disabled_without_any_key(db_session: AsyncSession) -> None:
    _override_settings(web_push_enabled=False)
    user = await make_user(db_session, role=Role.ARTISAN)
    async with _client() as client:
        response = await client.get("/api/v1/push/config", headers=_auth(user))
    assert response.json() == {"enabled": False, "vapid_public_key": None}


async def test_config_requires_a_client_or_artisan(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with _client() as client:
        anonymous = await client.get("/api/v1/push/config")
        as_admin = await client.get("/api/v1/push/config", headers=_auth(admin))
    assert anonymous.status_code == 401
    assert as_admin.status_code == 403


# ------------------------------------------------------------- abonnement


async def test_subscribe_stores_the_device(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    body = subscription()
    async with _client() as client:
        assert await _subscribe(client, user, body) == 204

    (row,) = await _rows(db_session, user)
    assert (row.endpoint, row.p256dh, row.auth) == (
        body["endpoint"],
        body["keys"]["p256dh"],
        body["keys"]["auth"],
    )


async def test_subscribing_again_is_idempotent_and_refreshes_the_keys(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    first = subscription()
    again = subscription(first["endpoint"])
    async with _client() as client:
        assert await _subscribe(client, user, first) == 204
        assert await _subscribe(client, user, again) == 204

    (row,) = await _rows(db_session, user)
    assert row.p256dh == again["keys"]["p256dh"]


async def test_a_shared_device_follows_the_account_now_signed_in(
    db_session: AsyncSession,
) -> None:
    before = await make_user(db_session, role=Role.CLIENT)
    after = await make_user(db_session, role=Role.ARTISAN)
    body = subscription()
    async with _client() as client:
        assert await _subscribe(client, before, body) == 204
        assert await _subscribe(client, after, body) == 204

    # L'ancien compte ne recevra plus rien sur cet appareil.
    assert await _rows(db_session, before) == []
    assert [row.endpoint for row in await _rows(db_session, after)] == [body["endpoint"]]


async def test_only_the_most_recent_devices_are_kept(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    bodies = [subscription() for _ in range(4)]  # plafond réglé à 3
    async with _client() as client:
        for body in bodies:
            assert await _subscribe(client, user, body) == 204

    assert [row.endpoint for row in await _rows(db_session, user)] == [
        body["endpoint"] for body in bodies[1:]
    ]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://attaquant.example/push",
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.attaquant.example/x",
    ],
)
async def test_an_endpoint_outside_the_push_services_is_refused(
    db_session: AsyncSession, endpoint: str
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        response = await client.post(
            "/api/v1/push/subscriptions", json=subscription(endpoint), headers=_auth(user)
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ABONNEMENT_PUSH_INVALIDE"
    assert await _rows(db_session, user) == []


@pytest.mark.parametrize(
    "keys",
    [
        {"p256dh": b64url_encode(b"\x04" + b"\x01" * 64)},  # hors de la courbe
        {"p256dh": "pas+du/base64url"},
        {"auth": b64url_encode(os.urandom(8))},  # secret trop court
    ],
)
async def test_malformed_browser_keys_are_refused(
    db_session: AsyncSession, keys: dict[str, str]
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        assert await _subscribe(client, user, subscription(**keys)) == 422
    assert await _rows(db_session, user) == []


async def test_an_oversized_endpoint_is_refused_by_the_schema(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        assert await _subscribe(client, user, subscription(FCM + "a" * 3000)) == 422


async def test_subscribing_is_refused_while_push_is_disabled(db_session: AsyncSession) -> None:
    _override_settings(web_push_enabled=False)
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        response = await client.post(
            "/api/v1/push/subscriptions", json=subscription(), headers=_auth(user)
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTIFICATIONS_PUSH_INDISPONIBLES"


async def test_subscriptions_are_rate_limited(db_session: AsyncSession) -> None:
    _override_settings(rate_limit_push_subscription_per_user_max=2)
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as client:
        statuses = [await _subscribe(client, user, subscription()) for _ in range(3)]
    assert statuses == [204, 204, 429]


async def test_admin_cannot_subscribe(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with _client() as client:
        assert await _subscribe(client, admin, subscription()) == 403


# ----------------------------------------------------------- désabonnement


async def test_unsubscribe_removes_only_ones_own_device(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, role=Role.CLIENT)
    other = await make_user(db_session, role=Role.ARTISAN)
    body = subscription()
    async with _client() as client:
        assert await _subscribe(client, owner, body) == 204
        # Un autre compte qui connaîtrait l'adresse : même réponse, rien supprimé.
        foreign = await client.request(
            "DELETE",
            "/api/v1/push/subscriptions",
            json={"endpoint": body["endpoint"]},
            headers=_auth(other),
        )
        assert foreign.status_code == 204
        assert len(await _rows(db_session, owner)) == 1

        own = await client.request(
            "DELETE",
            "/api/v1/push/subscriptions",
            json={"endpoint": body["endpoint"]},
            headers=_auth(owner),
        )
    assert own.status_code == 204
    assert await _rows(db_session, owner) == []


async def test_unsubscribe_works_even_with_push_disabled(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    body = subscription()
    async with _client() as client:
        assert await _subscribe(client, user, body) == 204
        _override_settings(web_push_enabled=False)
        response = await client.request(
            "DELETE",
            "/api/v1/push/subscriptions",
            json={"endpoint": body["endpoint"]},
            headers=_auth(user),
        )
    assert response.status_code == 204
    assert await _rows(db_session, user) == []


# ------------------------------------------------------- contraintes base


async def test_database_refuses_a_plain_http_endpoint(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    db_session.add(
        PushSubscription(user_id=user.id, endpoint="http://x.example/p", **browser_keys())
    )
    with pytest.raises(IntegrityError, match="ck_push_subscription_endpoint_https"):
        await db_session.flush()


async def test_subscriptions_disappear_with_the_account(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    db_session.add(PushSubscription(user_id=user.id, endpoint=f"{FCM}x", **browser_keys()))
    await db_session.flush()
    await db_session.execute(delete(User).where(User.id == user.id))
    count = await db_session.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == user.id)
    )
    assert count == 0
