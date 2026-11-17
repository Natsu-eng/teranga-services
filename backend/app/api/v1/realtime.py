"""Messagerie in-app : livraison temps réel par WebSocket (BUILD_PLAN.md §3.2,
Messagerie).

**Authentification par ticket, dans le sous-protocole.** Un navigateur ne
peut pas poser d'en-tête `Authorization` sur un WebSocket. Plutôt que de
mettre l'access token dans l'URL (il finirait dans les journaux des proxys
et serveurs), le front :

1. obtient un ticket par `POST /api/v1/realtime/ticket` (REST, authentifié) :
   jeton signé de type `"ws"` (refusé partout ailleurs), valable
   `WS_TICKET_TTL_SECONDS`, à USAGE UNIQUE ;
2. ouvre `wss://.../api/v1/realtime/ws` en proposant deux sous-protocoles :
   `teranga.v1` (version du protocole) et `ticket.<jeton>`.

Le serveur vérifie le ticket AVANT d'accepter la connexion ; sinon il
refuse la poignée de main (aucune connexion établie). Il ne renvoie que
`teranga.v1` : le ticket n'est jamais réémis.

**Protocole** (JSON, serveur -> client) : `message.created`,
`conversation.read`, `ping`. Le client répond `pong` aux pings (et peut
envoyer `ping`, le serveur répond `pong`). Le client n'ÉCRIT jamais de
message par ce canal : l'envoi passe par REST (app/api/v1/conversations.py).

Client -> serveur, en plus : `{"type": "viewing", "conversation_id": "<uuid>"
| null}` -- la conversation affichée à l'écran (null : aucune). Le serveur
n'en déduit qu'une chose : inutile d'envoyer une notification push pour un
message que l'utilisateur voit déjà arriver. Une valeur invalide vaut null ;
un utilisateur ne peut, au pire, que se priver lui-même de notifications.
"""

import asyncio
import contextlib
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.core.security import TokenInvalideError, decode_token, encode_ws_ticket
from app.db.session import SessionFactory, get_session_factory
from app.models.enums import Role
from app.models.user import User
from app.schemas.conversations import WsTicketOut
from app.services.realtime import connection_manager, ticket_store, viewing_presence

router = APIRouter(prefix="/realtime", tags=["realtime"])

PROTOCOL = "teranga.v1"
TICKET_PREFIX = "ticket."
# Codes de fermeture applicatifs (plage 4000-4999).
CLOSE_UNAUTHORIZED = 4401
CLOSE_HEARTBEAT_TIMEOUT = 4408

_ALLOWED_ROLES = frozenset({Role.CLIENT, Role.ARTISAN})


@router.post("/ticket", response_model=WsTicketOut)
async def create_ws_ticket(
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
) -> WsTicketOut:
    ticket, _jti = encode_ws_ticket(user, settings=settings)
    return WsTicketOut(ticket=ticket, expires_in=settings.ws_ticket_ttl_seconds)


class _SerializedSocket:
    """Enveloppe d'une WebSocket : les envois (diffusion d'un message,
    ping du battement de cœur) peuvent venir de tâches concurrentes ; un
    verrou garantit qu'ils partent l'un après l'autre, jamais entrelacés."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()

    async def send_json(self, data: Any, mode: str = "text") -> None:
        async with self._lock:
            await self._websocket.send_json(data, mode=mode)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        async with self._lock:
            await self._websocket.close(code=code, reason=reason)


def _offered_protocols(websocket: WebSocket) -> list[str]:
    raw = websocket.headers.get("sec-websocket-protocol", "")
    return [protocol.strip() for protocol in raw.split(",") if protocol.strip()]


async def _authenticate(
    protocols: list[str], *, session_factory: SessionFactory, settings: Settings
) -> User | None:
    """Utilisateur du ticket, ou `None` (ticket absent, invalide, expiré, déjà
    utilisé, d'un autre type, compte supprimé ou rôle non autorisé)."""
    if PROTOCOL not in protocols:
        return None
    ticket = next(
        (p.removeprefix(TICKET_PREFIX) for p in protocols if p.startswith(TICKET_PREFIX)), None
    )
    if not ticket:
        return None
    try:
        payload = decode_token(ticket, settings=settings)
        user_id = uuid.UUID(payload["sub"])
    except (TokenInvalideError, ValueError, KeyError):
        return None
    if payload["type"] != "ws":
        return None
    # Usage unique : un ticket intercepté puis rejoué est refusé.
    if not await ticket_store().consume(payload["jti"], expires_at=float(payload["exp"])):
        return None

    # Session ouverte le temps de cette vérification seulement.
    async with session_factory() as session:
        user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None or user.role not in _ALLOWED_ROLES:
        return None
    return user


def _viewed_conversation(raw: object) -> uuid.UUID | None:
    """Conversation signalée à l'écran, ou None (absente ou invalide)."""
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def _heartbeat(
    websocket: WebSocket,
    socket: _SerializedSocket,
    *,
    user_id: uuid.UUID,
    connection_id: str,
    settings: Settings,
) -> None:
    """Garde la connexion vivante et détecte une connexion morte : le serveur
    envoie un ping à intervalle régulier ; sans aucun signe du client
    (pong ou autre) avant le délai d'expiration, il ferme.

    Tient aussi à jour la présence « fil ouvert » de la connexion : posée ou
    effacée par `viewing`, RENOUVELÉE à chaque signe du client (les pongs
    suffisent) pour la durée d'expiration du battement de cœur."""
    last_seen = time.monotonic()
    viewing: uuid.UUID | None = None

    async def receive_loop() -> None:
        nonlocal last_seen, viewing
        while True:
            data = await websocket.receive_json()
            last_seen = time.monotonic()
            kind = data.get("type") if isinstance(data, dict) else None
            if kind == "ping":
                await socket.send_json({"type": "pong"})
            elif kind == "viewing" and isinstance(data, dict):
                viewing = _viewed_conversation(data.get("conversation_id"))
            # Tout autre message est ignoré : ce canal ne sert pas à écrire.
            if kind == "viewing" or viewing is not None:
                await viewing_presence().set_viewing(
                    user_id,
                    connection_id,
                    viewing,
                    ttl_seconds=settings.ws_heartbeat_timeout_seconds,
                )

    async def ping_loop() -> None:
        while True:
            await asyncio.sleep(settings.ws_heartbeat_interval_seconds)
            if time.monotonic() - last_seen > settings.ws_heartbeat_timeout_seconds:
                await socket.close(code=CLOSE_HEARTBEAT_TIMEOUT)
                return
            await socket.send_json({"type": "ping"})

    tasks = [asyncio.create_task(receive_loop()), asyncio.create_task(ping_loop())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            # Fin normale : déconnexion du client, JSON invalide, fermeture.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


@router.websocket("/ws")
async def realtime_socket(
    websocket: WebSocket,
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    user = await _authenticate(
        _offered_protocols(websocket), session_factory=session_factory, settings=settings
    )
    if user is None:
        # Fermer AVANT d'accepter : la poignée de main est refusée, aucune
        # connexion n'est établie, aucun détail n'est donné.
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    await websocket.accept(subprotocol=PROTOCOL)
    socket = _SerializedSocket(websocket)
    await connection_manager.register(
        user.id, socket, max_per_user=settings.ws_max_connections_per_user
    )
    # Identifiant aléatoire de CETTE connexion (présence « fil ouvert ») :
    # rien de dérivé de l'utilisateur ni du ticket.
    connection_id = uuid.uuid4().hex
    try:
        await _heartbeat(
            websocket, socket, user_id=user.id, connection_id=connection_id, settings=settings
        )
    finally:
        await connection_manager.unregister(user.id, socket)
        await viewing_presence().set_viewing(
            user.id, connection_id, None, ttl_seconds=settings.ws_heartbeat_timeout_seconds
        )
