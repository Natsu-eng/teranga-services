"""Livraison temps réel de la messagerie par WebSocket (BUILD_PLAN.md §3.2,
Messagerie).

**Rôle limité à la NOTIFICATION.** L'écriture d'un message passe toujours par
REST (validée, masquée, persistée) ; ce module ne fait que pousser aux
participants connectés ce qui vient d'être enregistré. Si aucun WebSocket
n'est ouvert, rien n'est perdu : le front relit l'historique par REST
(`GET .../messages?since=`), c'est son repli automatique.

**Un canal par utilisateur**, pas un par conversation : une seule connexion
par onglet suffit à alimenter à la fois le fil ouvert ET le badge de non-lus
de la navigation. L'isolation est structurelle : le serveur ne pousse un
événement qu'aux sockets des DEUX participants de la conversation concernée
(`publish(recipient_ids, ...)`) ; un client ne peut s'abonner à rien, il ne
peut donc jamais recevoir le fil d'autrui.

**Plusieurs instances (DEPLOYMENT.md)** : les connexions d'un utilisateur
vivent sur l'instance qui les a acceptées. La diffusion passe donc par un
`RealtimeBus` et l'usage unique des tickets par un `TicketStore` :

- sans `REDIS_URL` (dev, instance unique) : `LocalRealtimeBus` et
  `WsTicketRegistry`, en mémoire -- le comportement historique ;
- avec `REDIS_URL` : `RedisRealtimeBus` (pub/sub, chaque instance livre à
  ses propres connexions) et `RedisTicketStore` (un ticket consommé sur une
  instance est refusé partout), branchés au démarrage de l'application
  (`configure_realtime`, app/main.py).
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RealtimeSocket(Protocol):
    """Ce dont le gestionnaire a besoin d'une connexion (une WebSocket
    Starlette le fournit) — permet de le tester sans réseau."""

    async def send_json(self, data: Any, mode: str = "text") -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


# Code de fermeture applicatif (plage 4000-4999) quand une connexion est
# remplacée parce que l'utilisateur a dépassé son nombre de connexions.
CLOSE_TOO_MANY_CONNECTIONS = 4429


class ConnectionManager:
    """Connexions ouvertes, regroupées par utilisateur."""

    def __init__(self) -> None:
        # Ordre d'insertion conservé : la plus ancienne connexion d'un
        # utilisateur est la première à être fermée en cas de dépassement.
        self._connections: dict[uuid.UUID, OrderedDict[int, RealtimeSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self, user_id: uuid.UUID, socket: RealtimeSocket, *, max_per_user: int
    ) -> None:
        evicted: list[RealtimeSocket] = []
        async with self._lock:
            sockets = self._connections.setdefault(user_id, OrderedDict())
            sockets[id(socket)] = socket
            while len(sockets) > max_per_user:
                _, oldest = sockets.popitem(last=False)
                evicted.append(oldest)
        # Fermetures hors verrou : une socket lente ne bloque jamais les autres.
        for oldest in evicted:
            await _safe_close(oldest, CLOSE_TOO_MANY_CONNECTIONS)

    async def unregister(self, user_id: uuid.UUID, socket: RealtimeSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if sockets is None:
                return
            sockets.pop(id(socket), None)
            if not sockets:
                del self._connections[user_id]

    def connection_count(self, user_id: uuid.UUID) -> int:
        return len(self._connections.get(user_id, {}))

    async def publish(self, recipient_ids: tuple[uuid.UUID, ...], event: dict[str, Any]) -> None:
        """Pousse `event` à toutes les connexions des destinataires.

        Ne lève jamais : une connexion morte est retirée, les autres
        reçoivent quand même. L'appelant (route d'envoi) a DÉJÀ persisté le
        message ; un échec de diffusion ne doit jamais faire échouer l'envoi.
        """
        async with self._lock:
            targets = [
                (user_id, socket)
                for user_id in dict.fromkeys(recipient_ids)
                for socket in self._connections.get(user_id, {}).values()
            ]
        for user_id, socket in targets:
            try:
                await socket.send_json(event)
            except Exception:  # toute erreur d'envoi signifie une connexion morte
                logger.info("Connexion temps réel morte retirée (utilisateur %s).", user_id)
                await self.unregister(user_id, socket)


async def _safe_close(socket: RealtimeSocket, code: int) -> None:
    # Déjà fermée de l'autre côté : rien à faire.
    with contextlib.suppress(Exception):
        await socket.close(code=code)


class WsTicketRegistry:
    """Garantit l'usage UNIQUE d'un ticket WebSocket : son `jti` est consommé
    à la première connexion, tout rejeu est refusé. Les entrées expirent
    avec le ticket (aucune croissance illimitée)."""

    def __init__(self) -> None:
        self._consumed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def consume(self, jti: str, *, expires_at: float) -> bool:
        """Vrai si le ticket n'avait jamais servi (et le marque consommé)."""
        now = time.time()
        async with self._lock:
            for key in [k for k, exp in self._consumed.items() if exp <= now]:
                del self._consumed[key]
            if jti in self._consumed:
                return False
            self._consumed[jti] = expires_at
            return True


class RealtimeBus(Protocol):
    async def publish(
        self, recipient_ids: tuple[uuid.UUID, ...], event: dict[str, Any]
    ) -> None: ...


class TicketStore(Protocol):
    async def consume(self, jti: str, *, expires_at: float) -> bool: ...


class LocalRealtimeBus:
    """Instance unique : livre directement aux connexions de ce processus."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    async def publish(self, recipient_ids: tuple[uuid.UUID, ...], event: dict[str, Any]) -> None:
        await self._manager.publish(recipient_ids, event)


# Connexions de CE processus (toujours locales, par nature).
connection_manager = ConnectionManager()
ws_ticket_registry = WsTicketRegistry()

# Implémentations actives : locales par défaut, remplacées par Redis au
# démarrage si REDIS_URL est renseignée (voir `configure_realtime`).
_bus: RealtimeBus = LocalRealtimeBus(connection_manager)
_ticket_store: TicketStore = ws_ticket_registry


def realtime_bus() -> RealtimeBus:
    return _bus


def ticket_store() -> TicketStore:
    return _ticket_store


def configure_realtime(bus: RealtimeBus, store: TicketStore) -> None:
    global _bus, _ticket_store
    _bus, _ticket_store = bus, store


def reset_realtime() -> None:
    """Retour aux implémentations locales (arrêt de l'application, tests)."""
    configure_realtime(LocalRealtimeBus(connection_manager), ws_ticket_registry)


def message_created_event(message: dict[str, Any]) -> dict[str, Any]:
    """Événement diffusé aux deux participants quand un message est enregistré."""
    return {"type": "message.created", "message": message}


def conversation_read_event(conversation_id: uuid.UUID, last_read_seq: int) -> dict[str, Any]:
    """Diffusé aux AUTRES connexions du lecteur (autres onglets/appareils) :
    leurs badges de non-lus se mettent à jour sans attendre."""
    return {
        "type": "conversation.read",
        "conversation_id": str(conversation_id),
        "last_read_seq": last_read_seq,
    }
