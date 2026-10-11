"""Livraison temps réel par WebSocket (`/api/v1/realtime`).

Exécutés en ASGI pur (httpx-ws), sur la même boucle et la même session
transactionnelle que les tests REST : l'application réelle est exercée, la
base de dev n'est jamais modifiée durablement.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest
from httpx import AsyncClient
from httpx_ws import (
    AsyncWebSocketSession,
    WebSocketDisconnect,
    WebSocketUpgradeError,
    aconnect_ws,
)
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token, encode_ws_ticket
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.enums import Role
from app.models.user import User
from app.services.contact_masking import PHONE_PLACEHOLDER
from tests.factories import make_engagement, make_user

WS_URL = "/api/v1/realtime/ws"


@pytest.fixture(autouse=True)
def _override_dependencies(db_session: AsyncSession) -> Generator[None, None, None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    @asynccontextmanager
    async def _test_session_scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_session_factory] = lambda: _test_session_scope
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_session_factory, None)
    app.dependency_overrides.pop(get_settings, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGIWebSocketTransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


def _override_settings(**changes: Any) -> None:
    settings = get_settings().model_copy(update=changes)
    app.dependency_overrides[get_settings] = lambda: settings


async def _ticket(client: AsyncClient, user: User) -> str:
    response = await client.post("/api/v1/realtime/ticket", headers=_auth(user))
    assert response.status_code == 200, response.text
    ticket: str = response.json()["ticket"]
    return ticket


def _protocols(ticket: str) -> list[str]:
    return ["teranga.v1", f"ticket.{ticket}"]


def _connect(
    client: AsyncClient, protocols: list[str]
) -> AbstractAsyncContextManager[AsyncWebSocketSession]:
    """Ouvre la connexion temps réel en proposant ces sous-protocoles."""
    return aconnect_ws(WS_URL, client, subprotocols=protocols)


async def _assert_refused(client: AsyncClient, protocols: list[str]) -> None:
    with pytest.raises((WebSocketUpgradeError, WebSocketDisconnect)):
        async with _connect(client, protocols) as ws:
            await ws.receive_json()


async def _nothing_received(ws: AsyncWebSocketSession, seconds: float = 0.3) -> bool:
    try:
        await asyncio.wait_for(ws.receive_json(), timeout=seconds)
    except TimeoutError:
        return True
    return False


# ------------------------------------------------------------------ Ticket


async def test_ticket_requires_authentication() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/realtime/ticket")

    assert response.status_code == 401


async def test_ticket_cannot_be_used_as_a_rest_access_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        ticket = await _ticket(client, user)
        response = await client.get(
            "/api/v1/conversations/me", headers={"Authorization": f"Bearer {ticket}"}
        )

    assert response.status_code == 401


async def test_ticket_cannot_be_used_as_a_refresh_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        ticket = await _ticket(client, user)
        response = await client.post("/api/v1/auth/refresh", json={"refresh": ticket})

    assert response.status_code == 401


# ------------------------------------------------------------------ Authentification WS


async def test_connection_refused_without_ticket() -> None:
    async with _client() as client:
        await _assert_refused(client, ["teranga.v1"])


async def test_connection_refused_with_a_forged_ticket() -> None:
    async with _client() as client:
        await _assert_refused(client, _protocols("pas.un.jeton"))


async def test_connection_refused_with_an_access_token_instead_of_a_ticket(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        await _assert_refused(client, _protocols(encode_access_token(user)))


async def test_connection_refused_without_the_protocol_version(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        ticket = await _ticket(client, user)
        await _assert_refused(client, [f"ticket.{ticket}"])


async def test_ticket_is_single_use(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        ticket = await _ticket(client, user)
        async with _connect(client, _protocols(ticket)) as ws:
            assert ws.subprotocol == "teranga.v1"
        # Le même ticket, rejoué : refusé.
        await _assert_refused(client, _protocols(ticket))


async def test_admin_is_refused_even_with_a_valid_ticket(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    ticket, _jti = encode_ws_ticket(admin)

    async with _client() as client:
        await _assert_refused(client, _protocols(ticket))


# ------------------------------------------------------------------ Livraison


async def test_both_participants_receive_a_new_message_live(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        client_ticket = await _ticket(client, engagement.client)
        artisan_ticket = await _ticket(client, engagement.artisan_user)
        async with (
            _connect(client, _protocols(client_ticket)) as client_ws,
            _connect(client, _protocols(artisan_ticket)) as artisan_ws,
        ):
            sent = await client.post(
                f"/api/v1/conversations/{engagement.conversation.id}/messages",
                json={"body": "Mon numéro : 77 123 45 67"},
                headers=_auth(engagement.client),
            )
            to_artisan = await asyncio.wait_for(artisan_ws.receive_json(), timeout=2)
            to_sender = await asyncio.wait_for(client_ws.receive_json(), timeout=2)

    assert sent.status_code == 201
    assert to_artisan["type"] == "message.created"
    assert to_artisan["message"]["id"] == sent.json()["id"]
    assert to_artisan["message"]["conversation_id"] == str(engagement.conversation.id)
    # Ce qui est diffusé est déjà masqué, exactement comme la réponse REST.
    assert to_artisan["message"]["body"] == f"Mon numéro : {PHONE_PLACEHOLDER}"
    assert to_artisan["message"]["contact_masked"] is True
    # L'expéditeur la reçoit aussi (ses autres onglets / appareils).
    assert to_sender["message"]["id"] == sent.json()["id"]


async def test_a_third_party_never_receives_someone_elses_messages(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        outsider_ticket = await _ticket(client, outsider)
        async with _connect(client, _protocols(outsider_ticket)) as ws:
            sent = await client.post(
                f"/api/v1/conversations/{engagement.conversation.id}/messages",
                json={"body": "Message privé"},
                headers=_auth(engagement.client),
            )
            assert sent.status_code == 201
            assert await _nothing_received(ws)


async def test_reading_notifies_the_readers_other_connections_only(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        sent = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": "Bonjour"},
            headers=_auth(engagement.artisan_user),
        )
        client_ticket = await _ticket(client, engagement.client)
        artisan_ticket = await _ticket(client, engagement.artisan_user)
        async with (
            _connect(client, _protocols(client_ticket)) as client_ws,
            _connect(client, _protocols(artisan_ticket)) as artisan_ws,
        ):
            await client.post(
                f"/api/v1/conversations/{engagement.conversation.id}/read",
                json={"last_read_seq": sent.json()["seq"]},
                headers=_auth(engagement.client),
            )
            event = await asyncio.wait_for(client_ws.receive_json(), timeout=2)
            assert await _nothing_received(artisan_ws)

    assert event == {
        "type": "conversation.read",
        "conversation_id": str(engagement.conversation.id),
        "last_read_seq": sent.json()["seq"],
    }


# ------------------------------------------------------------------ Robustesse


async def test_oldest_connection_is_closed_beyond_the_per_user_cap(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    _override_settings(ws_max_connections_per_user=1)

    async with _client() as client:
        first_ticket = await _ticket(client, user)
        second_ticket = await _ticket(client, user)
        # Ouvertes dans l'ordre : la première, puis la seconde qui la remplace.
        async with (
            _connect(client, _protocols(first_ticket)) as first,
            _connect(client, _protocols(second_ticket)),
        ):
            with pytest.raises(WebSocketDisconnect) as closed:
                await asyncio.wait_for(first.receive_json(), timeout=2)

    assert closed.value.code == 4429


async def test_server_answers_a_client_ping(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        ticket = await _ticket(client, user)
        async with _connect(client, _protocols(ticket)) as ws:
            await ws.send_json({"type": "ping"})
            reply = await asyncio.wait_for(ws.receive_json(), timeout=2)

    assert reply == {"type": "pong"}


async def test_heartbeat_pings_then_closes_a_silent_connection(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    _override_settings(ws_heartbeat_interval_seconds=0.05, ws_heartbeat_timeout_seconds=0.2)

    async with _client() as client:
        ticket = await _ticket(client, user)
        async with _connect(client, _protocols(ticket)) as ws:
            ping = await asyncio.wait_for(ws.receive_json(), timeout=2)
            # Le client ne répond jamais : la connexion finit fermée.
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    await asyncio.wait_for(ws.receive_json(), timeout=2)

    assert ping == {"type": "ping"}
    assert closed.value.code == 4408


async def test_answering_pongs_keeps_the_connection_alive(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    _override_settings(ws_heartbeat_interval_seconds=0.05, ws_heartbeat_timeout_seconds=0.2)

    async with _client() as client:
        ticket = await _ticket(client, user)
        async with _connect(client, _protocols(ticket)) as ws:
            # Bien au-delà du délai d'expiration, en répondant à chaque ping.
            for _ in range(10):
                event = await asyncio.wait_for(ws.receive_json(), timeout=2)
                assert event == {"type": "ping"}
                await ws.send_json({"type": "pong"})
