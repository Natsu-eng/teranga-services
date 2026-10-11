"""Gestionnaire de connexions et registre de tickets (app.services.realtime),
testés sans réseau avec de fausses connexions."""

import time
import uuid
from typing import Any

from app.services.realtime import (
    CLOSE_TOO_MANY_CONNECTIONS,
    ConnectionManager,
    WsTicketRegistry,
)


class FakeSocket:
    def __init__(self, *, broken: bool = False) -> None:
        self.sent: list[Any] = []
        self.closed_with: int | None = None
        self._broken = broken

    async def send_json(self, data: Any, mode: str = "text") -> None:
        if self._broken:
            raise RuntimeError("connexion coupée")
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed_with = code


async def test_publish_reaches_every_connection_of_every_recipient() -> None:
    manager = ConnectionManager()
    alice, bob = uuid.uuid4(), uuid.uuid4()
    alice_phone, alice_laptop, bob_phone = FakeSocket(), FakeSocket(), FakeSocket()
    for user, socket in ((alice, alice_phone), (alice, alice_laptop), (bob, bob_phone)):
        await manager.register(user, socket, max_per_user=5)

    await manager.publish((alice, bob), {"type": "message.created"})

    assert alice_phone.sent == alice_laptop.sent == bob_phone.sent == [{"type": "message.created"}]


async def test_publish_ignores_users_without_connection_and_never_duplicates() -> None:
    manager = ConnectionManager()
    alice = uuid.uuid4()
    socket = FakeSocket()
    await manager.register(alice, socket, max_per_user=5)

    # Destinataire répété (ex. un participant qui s'écrit) et absent.
    await manager.publish((alice, alice, uuid.uuid4()), {"type": "ping"})

    assert socket.sent == [{"type": "ping"}]


async def test_a_dead_connection_is_dropped_without_affecting_the_others() -> None:
    manager = ConnectionManager()
    alice = uuid.uuid4()
    dead, alive = FakeSocket(broken=True), FakeSocket()
    await manager.register(alice, dead, max_per_user=5)
    await manager.register(alice, alive, max_per_user=5)

    await manager.publish((alice,), {"type": "message.created"})

    assert alive.sent == [{"type": "message.created"}]
    assert manager.connection_count(alice) == 1


async def test_the_oldest_connection_is_closed_beyond_the_cap() -> None:
    manager = ConnectionManager()
    alice = uuid.uuid4()
    oldest, middle, newest = FakeSocket(), FakeSocket(), FakeSocket()
    for socket in (oldest, middle, newest):
        await manager.register(alice, socket, max_per_user=2)

    assert oldest.closed_with == CLOSE_TOO_MANY_CONNECTIONS
    assert middle.closed_with is None and newest.closed_with is None
    assert manager.connection_count(alice) == 2


async def test_unregister_forgets_the_user_once_disconnected() -> None:
    manager = ConnectionManager()
    alice = uuid.uuid4()
    socket = FakeSocket()
    await manager.register(alice, socket, max_per_user=5)

    await manager.unregister(alice, socket)
    await manager.unregister(alice, socket)  # idempotent

    assert manager.connection_count(alice) == 0


async def test_a_ticket_can_only_be_consumed_once() -> None:
    registry = WsTicketRegistry()
    expires_at = time.time() + 60

    assert await registry.consume("jti-1", expires_at=expires_at) is True
    assert await registry.consume("jti-1", expires_at=expires_at) is False
    assert await registry.consume("jti-2", expires_at=expires_at) is True


async def test_expired_entries_are_purged() -> None:
    registry = WsTicketRegistry()
    await registry.consume("ancien", expires_at=time.time() - 1)

    # Une consommation suivante purge l'entrée expirée (pas de croissance
    # illimitée) ; un ticket expiré est de toute façon refusé en amont par
    # la vérification de signature (claim `exp`).
    await registry.consume("nouveau", expires_at=time.time() + 60)

    assert "ancien" not in registry._consumed
