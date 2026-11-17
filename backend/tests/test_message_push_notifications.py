"""Notification push à l'envoi d'un message (app/services/message_notifications.py,
déclenchée par app/api/v1/conversations.py).

Application réelle en ASGI (la tâche d'arrière-plan s'exécute avant le
retour du client de test), base de dev dans une transaction annulée. Le
service de push est remplacé par un faux expéditeur qui enregistre chaque
envoi : aucun réseau.
"""

import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.core.vapid import generate_key_pair
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.push import PushSubscription
from app.models.user import User
from app.services import message_notifications
from app.services.message_notifications import notify_new_message
from app.services.rate_limit import SlidingWindowRateLimiter, get_message_send_rate_limiter
from app.services.realtime import LocalViewingPresence, configure_realtime, reset_realtime
from app.services.web_push import (
    PushNotification,
    PushOutcome,
    PushResult,
    PushTarget,
)
from tests.factories import Engagement, make_engagement
from tests.test_push_subscriptions import browser_keys

FCM = "https://fcm.googleapis.com/fcm/send/"


class FakeSender:
    """Faux service de push : enregistre les envois, répond selon l'adresse."""

    def __init__(self, outcomes: dict[str, PushOutcome] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.sent: list[tuple[PushTarget, PushNotification]] = []

    async def send(self, target: PushTarget, notification: PushNotification) -> PushResult:
        self.sent.append((target, notification))
        outcome = self.outcomes.get(target.endpoint, PushOutcome.DELIVERED)
        detail = {PushOutcome.GONE: "HTTP 410", PushOutcome.FAILED: "HTTP 500"}.get(outcome, "ok")
        return PushResult(outcome, detail)

    @property
    def endpoints(self) -> list[str]:
        return [target.endpoint for target, _ in self.sent]


def _push_settings() -> Settings:
    public_key, private_key = generate_key_pair()
    return get_settings().model_copy(
        update={
            "web_push_enabled": True,
            "vapid_public_key": public_key,
            "vapid_private_key": private_key,
            "vapid_subject": "mailto:contact@teranga.example",
        }
    )


@pytest.fixture
def presence() -> Generator[LocalViewingPresence, None, None]:
    """Présence locale neuve, branchée sur l'application le temps du test."""
    from app.services.realtime import realtime_bus, ticket_store

    local = LocalViewingPresence()
    configure_realtime(realtime_bus(), ticket_store(), local)
    yield local
    reset_realtime()


@pytest.fixture
def sender(monkeypatch: pytest.MonkeyPatch) -> FakeSender:
    fake = FakeSender()
    monkeypatch.setattr(message_notifications, "WebPushSender", lambda _settings: fake)
    return fake


@pytest.fixture(autouse=True)
def _app(db_session: AsyncSession) -> Generator[None, None, None]:
    settings = _push_settings()

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_session_factory] = lambda: _scope
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_message_send_rate_limiter] = lambda: limiter
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _subscribe_device(session: AsyncSession, user: User) -> str:
    endpoint = f"{FCM}{uuid.uuid4().hex}"
    session.add(PushSubscription(user_id=user.id, endpoint=endpoint, **browser_keys()))
    await session.flush()
    return endpoint


async def _send(engagement: Engagement, sender: User, body: str = "Bonjour") -> Any:
    async with _client() as client:
        response = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": body},
            headers=_auth(sender),
        )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------- destinataire seul


async def test_only_the_recipient_devices_are_notified(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    phone = await _subscribe_device(db_session, engagement.artisan_user)
    laptop = await _subscribe_device(db_session, engagement.artisan_user)
    await _subscribe_device(db_session, engagement.client)  # l'expéditeur

    await _send(engagement, engagement.client)

    assert sorted(sender.endpoints) == sorted([phone, laptop])


async def test_the_other_direction_notifies_the_client(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    client_device = await _subscribe_device(db_session, engagement.client)
    await _subscribe_device(db_session, engagement.artisan_user)

    await _send(engagement, engagement.artisan_user)

    assert sender.endpoints == [client_device]


async def test_the_content_is_sober_and_opens_the_conversation(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)

    await _send(engagement, engagement.client, "Appelez-moi au 77 123 45 67, code 4821")

    ((_, notification),) = sender.sent
    conversation_id = engagement.conversation.id
    assert notification == PushNotification(
        title="Téranga",
        body="Nouveau message sur Téranga",
        url=f"/messages/{conversation_id}",
        tag=f"conversation-{conversation_id}",
        topic=conversation_id.hex,
    )
    payload = notification.payload().decode()
    for leak in ("77", "4821", "Appelez", engagement.client.full_name, engagement.client.phone):
        assert leak not in payload


# ---------------------------------------------------- fil déjà à l'écran


async def test_no_push_while_the_recipient_has_the_conversation_open(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)
    await presence.set_viewing(
        engagement.artisan_user.id, "onglet", engagement.conversation.id, ttl_seconds=60
    )

    await _send(engagement, engagement.client)

    assert sender.sent == []


async def test_push_when_the_recipient_looks_at_another_conversation(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)
    await presence.set_viewing(engagement.artisan_user.id, "onglet", uuid.uuid4(), ttl_seconds=60)

    await _send(engagement, engagement.client)

    assert len(sender.sent) == 1


async def test_the_sender_viewing_the_conversation_does_not_mute_the_recipient(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)
    await presence.set_viewing(
        engagement.client.id, "onglet", engagement.conversation.id, ttl_seconds=60
    )

    await _send(engagement, engagement.client)

    assert len(sender.sent) == 1


# ------------------------------------------------------------ best-effort


async def test_dead_subscriptions_are_removed_and_the_others_kept(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    alive = await _subscribe_device(db_session, engagement.artisan_user)
    gone = await _subscribe_device(db_session, engagement.artisan_user)
    failing = await _subscribe_device(db_session, engagement.artisan_user)
    sender.outcomes = {gone: PushOutcome.GONE, failing: PushOutcome.FAILED}

    message = await _send(engagement, engagement.client)

    remaining = await db_session.scalars(
        select(PushSubscription.endpoint).where(
            PushSubscription.user_id == engagement.artisan_user.id
        )
    )
    # Un échec passager (500) ne supprime rien ; seul 404/410 le fait.
    assert sorted(remaining) == sorted([alive, failing])
    assert message["body"] == "Bonjour"


class ExplodingSender:
    async def send(self, target: PushTarget, notification: PushNotification) -> PushResult:
        raise RuntimeError("service de push en panne")


async def test_a_push_failure_never_fails_the_message(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    presence: LocalViewingPresence,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(message_notifications, "WebPushSender", lambda _s: ExplodingSender())
    engagement = await make_engagement(db_session)
    endpoint = await _subscribe_device(db_session, engagement.artisan_user)

    with caplog.at_level(logging.INFO):
        message = await _send(engagement, engagement.client)

    assert message["seq"] >= 1  # message enregistré et renvoyé normalement
    assert "1 échec(s) (RuntimeError x1)" in caplog.text
    assert endpoint not in caplog.text  # jamais d'adresse d'abonnement en journal


async def test_nothing_is_attempted_while_push_is_disabled(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    disabled = app.dependency_overrides[get_settings]().model_copy(
        update={"web_push_enabled": False}
    )
    app.dependency_overrides[get_settings] = lambda: disabled
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)

    await _send(engagement, engagement.client)

    assert sender.sent == []


async def test_a_deleted_recipient_is_never_notified(
    db_session: AsyncSession, sender: FakeSender, presence: LocalViewingPresence
) -> None:
    engagement = await make_engagement(db_session)
    await _subscribe_device(db_session, engagement.artisan_user)
    engagement.artisan_user.deleted_at = datetime.now(UTC)
    await db_session.flush()

    await notify_new_message(
        engagement.artisan_user.id,
        engagement.conversation.id,
        app.dependency_overrides[get_settings](),
        app.dependency_overrides[get_session_factory](),
        presence=presence,
    )

    assert sender.sent == []


async def test_an_unexpected_error_is_logged_without_raising(
    caplog: pytest.LogCaptureFixture, presence: LocalViewingPresence
) -> None:
    @asynccontextmanager
    async def broken_scope() -> AsyncIterator[AsyncSession]:
        raise ConnectionError("base injoignable")
        yield  # pragma: no cover

    await notify_new_message(
        uuid.uuid4(),
        uuid.uuid4(),
        app.dependency_overrides[get_settings](),
        broken_scope,
        presence=presence,
    )  # ne lève rien
    assert "Push nouveau message NON envoyé : ConnectionError." in caplog.text
