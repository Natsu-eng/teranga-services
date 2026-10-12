"""Implémentations Redis des états partagés entre instances (DEPLOYMENT.md,
dettes multi-instance de BUILD_PLAN.md §3.4).

Actives seulement si `REDIS_URL` est renseignée ; sinon, chaque service
garde son implémentation actuelle (mémoire en dev, PostgreSQL pour le rate
limiting hors dev) -- le dev tourne exactement comme avant, sans Redis.

Trois usages, chacun derrière l'interface déjà en place :

- `RedisRateLimiter` (contrat `RateLimiter`) : fenêtre glissante dans un
  ensemble trié, en UN script Lua atomique (aucune course entre instances).
  Horloge : celle du serveur Redis (`TIME`), commune à toutes les instances.
- `RedisTicketStore` : usage unique d'un ticket WebSocket, `SET NX` avec
  expiration à celle du ticket.
- `RedisRealtimeBus` : diffusion d'un événement à TOUTES les instances
  (pub/sub) ; chacune le pousse à ses propres connexions.

Les clés ne contiennent jamais de donnée personnelle en clair : le rate
limiting stocke une empreinte (`hash_rate_limit_key`), les tickets leur
identifiant aléatoire (`jti`).

Pannes Redis :
- rate limiting et tickets : échec FERMÉ (l'exception remonte, la requête
  est refusée) -- jamais une limite ou un usage unique levés en silence ;
- diffusion temps réel : échec OUVERT -- journalisé, l'envoi du message
  (déjà enregistré) n'échoue jamais ; le front relit l'historique par REST.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from redis.asyncio import Redis

# `rate_limit` n'importe ce module que tardivement (à la sélection) : pas de cycle.
from app.services.rate_limit import hash_rate_limit_key, validate_window

logger = logging.getLogger(__name__)

# Préfixe de toutes les clés : une même instance Redis peut être partagée
# sans collision avec d'autres usages.
KEY_PREFIX = "teranga"
REALTIME_CHANNEL = f"{KEY_PREFIX}:realtime"

# Fenêtre glissante atomique : purge des appels sortis de la fenêtre,
# comptage, puis enregistrement si sous la limite. Renvoie 1 (autorisé) ou
# 0 (refusé, NON décompté -- même contrat que les autres stockages).
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local max_hits = tonumber(ARGV[2])
local member = ARGV[3]
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
if redis.call('ZCARD', key) >= max_hits then
  return 0
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return 1
"""


def create_redis_client(url: str) -> "Redis":
    """Client Redis asynchrone (connexions mutualisées, réponses décodées).
    Délais bornés : une panne Redis ne fait jamais pendre une requête."""
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )


_clients: dict[str, "Redis"] = {}


def get_redis_client(url: str) -> "Redis":
    """Client unique par processus (et par URL) : un seul pool de connexions
    partagé par le rate limiting, les tickets et la diffusion temps réel."""
    if url not in _clients:
        _clients[url] = create_redis_client(url)
    return _clients[url]


def forget_redis_client(url: str) -> None:
    """Oublie le client (arrêt de l'application) : un client fermé n'est
    jamais réutilisé."""
    _clients.pop(url, None)


class RedisRateLimiter:
    """Fenêtre glissante partagée par toutes les instances (contrat
    `app.services.rate_limit.RateLimiter`)."""

    def __init__(self, client: "Redis", bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._script = client.register_script(_SLIDING_WINDOW_LUA)

    async def check(self, key: str, *, max_hits: int, window_seconds: int) -> bool:
        validate_window(window_seconds)
        redis_key = f"{KEY_PREFIX}:rl:{self._bucket}:{hash_rate_limit_key(self._bucket, key)}"
        allowed = await self._script(
            keys=[redis_key], args=[window_seconds * 1000, max_hits, uuid.uuid4().hex]
        )
        return int(allowed) == 1


class RedisTicketStore:
    """Usage unique des tickets WebSocket, partagé par toutes les instances :
    un ticket consommé sur l'instance A est refusé sur l'instance B."""

    def __init__(self, client: "Redis") -> None:
        self._client = client

    async def consume(self, jti: str, *, expires_at: float) -> bool:
        ttl_ms = max(1, int((expires_at - time.time()) * 1000))
        created = await self._client.set(f"{KEY_PREFIX}:ws-ticket:{jti}", "1", nx=True, px=ttl_ms)
        return bool(created)


# Livraison locale : pousse un événement aux connexions de CETTE instance.
LocalDelivery = Callable[[tuple[uuid.UUID, ...], dict[str, Any]], Awaitable[None]]


class RedisRealtimeBus:
    """Diffusion inter-instances par pub/sub Redis.

    `publish` envoie l'événement sur le canal commun ; chaque instance (y
    compris l'émettrice) le reçoit par son abonnement (`run`) et le livre à
    ses propres connexions. Le message transporte uniquement les
    destinataires et l'événement déjà autorisé par la route : l'isolation
    reste celle du gestionnaire local (seuls les deux participants)."""

    def __init__(self, client: "Redis", deliver_locally: LocalDelivery) -> None:
        self._client = client
        self._deliver_locally = deliver_locally

    async def publish(self, recipient_ids: tuple[uuid.UUID, ...], event: dict[str, Any]) -> None:
        payload = json.dumps({"to": [str(u) for u in recipient_ids], "event": event})
        try:
            await self._client.publish(REALTIME_CHANNEL, payload)
        except Exception:
            # Échec OUVERT : le message est déjà enregistré, le front le
            # relira par REST (repli polling). Jamais d'erreur pour l'envoi.
            logger.exception("Diffusion temps réel via Redis impossible.")

    async def handle(self, raw: str) -> None:
        """Livre localement un message reçu du canal (ignore un message mal formé)."""
        try:
            data = json.loads(raw)
            recipients = tuple(uuid.UUID(value) for value in data["to"])
            event = data["event"]
        except (ValueError, KeyError, TypeError):
            logger.warning("Message temps réel Redis ignoré (format inattendu).")
            return
        await self._deliver_locally(recipients, event)

    async def run(self) -> None:
        """Boucle d'abonnement (tâche de fond de l'application). Se
        réabonne après une coupure Redis, avec une attente croissante."""
        delay = 1.0
        while True:
            try:
                async with self._client.pubsub() as pubsub:
                    await pubsub.subscribe(REALTIME_CHANNEL)
                    delay = 1.0
                    async for message in pubsub.listen():
                        if message.get("type") == "message":
                            await self.handle(str(message["data"]))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Abonnement temps réel Redis interrompu, reprise dans %ss.", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)


async def close_quietly(client: "Redis") -> None:
    with contextlib.suppress(Exception):
        await client.aclose()


@contextlib.asynccontextmanager
async def realtime_over_redis(redis_url: str | None) -> AsyncIterator[None]:
    """Cycle de vie de l'application : si REDIS_URL est renseignée, branche
    la diffusion temps réel et les tickets sur Redis et lance l'abonnement
    de fond ; à l'arrêt, le coupe et ferme le client. Sans REDIS_URL : ne
    fait rien (implémentations locales, comportement historique)."""
    if not redis_url:
        yield
        return
    # Import tardif : `realtime` n'a pas à connaître Redis.
    from app.services.realtime import configure_realtime, connection_manager, reset_realtime

    client = get_redis_client(redis_url)
    bus = RedisRealtimeBus(client, connection_manager.publish)
    configure_realtime(bus, RedisTicketStore(client))
    listener = asyncio.create_task(bus.run(), name="realtime-redis-subscriber")
    logger.info("Temps réel et tickets WebSocket partagés via Redis.")
    try:
        yield
    finally:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
        reset_realtime()
        await close_quietly(client)
        forget_redis_client(redis_url)
