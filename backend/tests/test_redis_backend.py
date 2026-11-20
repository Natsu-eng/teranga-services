"""Redis pour les états partagés entre instances (app/services/redis_backend.py).

`fakeredis` : un vrai serveur Redis simulé en mémoire (script Lua et pub/sub
compris), sans réseau. Plusieurs clients sur le même `FakeServer` jouent le
rôle de plusieurs instances du backend.
"""

import asyncio
import time
import uuid
from collections.abc import Iterator
from typing import Any

import fakeredis
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import rate_limit, redis_backend
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter
from app.services.realtime import (
    LocalRealtimeBus,
    WsTicketRegistry,
    realtime_bus,
    ticket_store,
)
from app.services.redis_backend import (
    RedisRateLimiter,
    RedisRealtimeBus,
    RedisTicketStore,
    realtime_over_redis,
)
from tests.deployed_settings import DEPLOYED_REQUIRED

REDIS_URL = "redis://redis.test:6379/0"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
        **DEPLOYED_REQUIRED,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def _client(server: fakeredis.FakeServer) -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)


@pytest.fixture
def fake_redis(server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`get_redis_client` renvoie un client du serveur simulé ; les caches
    de limiteurs sont isolés par test."""
    monkeypatch.setattr(redis_backend, "get_redis_client", lambda _url: _client(server))
    monkeypatch.setattr(rate_limit, "_redis_limiters", {})
    yield


# ------------------------------------------------------------------ sélection


def test_redis_is_selected_when_redis_url_is_set_otherwise_memory() -> None:
    assert _settings(redis_url=REDIS_URL).rate_limit_backend == "redis"
    assert _settings(redis_url="").rate_limit_backend == "memory"
    assert _settings().rate_limit_backend == "memory"
    assert _settings(environment="staging").rate_limit_backend == "postgres"
    assert _settings(environment="staging", redis_url=REDIS_URL).rate_limit_backend == "redis"


def test_redis_backend_without_url_and_bad_scheme_are_refused() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_BACKEND=redis exige REDIS_URL"):
        _settings(rate_limit_backend="redis")
    with pytest.raises(ValidationError, match="REDIS_URL doit commencer"):
        _settings(redis_url="http://redis:6379")


def test_dependency_serves_redis_or_memory(fake_redis: None) -> None:
    assert isinstance(get_otp_rate_limiter(_settings(redis_url=REDIS_URL)), RedisRateLimiter)
    assert isinstance(get_otp_rate_limiter(_settings()), SlidingWindowRateLimiter)


def test_without_redis_realtime_stays_in_memory() -> None:
    assert isinstance(realtime_bus(), LocalRealtimeBus)
    assert isinstance(ticket_store(), WsTicketRegistry)


# -------------------------------------------------------------- rate limiting


async def test_redis_limit_is_shared_by_every_instance(server: fakeredis.FakeServer) -> None:
    instance_a = RedisRateLimiter(_client(server), "otp")
    instance_b = RedisRateLimiter(_client(server), "otp")

    results = [
        await instance_a.check("+221771234567", max_hits=3, window_seconds=60),
        await instance_b.check("+221771234567", max_hits=3, window_seconds=60),
        await instance_a.check("+221771234567", max_hits=3, window_seconds=60),
        await instance_b.check("+221771234567", max_hits=3, window_seconds=60),
    ]

    assert results == [True, True, True, False]
    # Une autre clé, un autre bucket : compteurs indépendants.
    assert await instance_a.check("+221770000000", max_hits=3, window_seconds=60)
    assert await RedisRateLimiter(_client(server), "ai").check(
        "+221771234567", max_hits=3, window_seconds=60
    )


async def test_redis_refusals_are_not_counted_and_the_window_slides(
    server: fakeredis.FakeServer,
) -> None:
    limiter = RedisRateLimiter(_client(server), "otp")
    assert await limiter.check("ip", max_hits=1, window_seconds=1)
    for _ in range(3):
        assert not await limiter.check("ip", max_hits=1, window_seconds=1)

    await asyncio.sleep(1.1)

    assert await limiter.check("ip", max_hits=1, window_seconds=1)


async def test_redis_keys_never_contain_the_raw_identifier(server: fakeredis.FakeServer) -> None:
    client = _client(server)
    await RedisRateLimiter(client, "otp").check("+221771234567", max_hits=3, window_seconds=60)

    keys = [key async for key in client.scan_iter("*")]
    assert keys and all("221771234567" not in key for key in keys)
    # Les compteurs expirent avec la fenêtre : rien ne reste indéfiniment.
    ttls = [await client.pttl(key) for key in keys]
    assert all(0 < ttl <= 60_000 for ttl in ttls)


async def test_redis_limiter_rejects_an_invalid_window(server: fakeredis.FakeServer) -> None:
    with pytest.raises(ValueError, match="Fenêtre de rate limiting invalide"):
        await RedisRateLimiter(_client(server), "otp").check("k", max_hits=1, window_seconds=0)


# --------------------------------------------------------------------- tickets


async def test_a_ticket_is_single_use_across_instances(server: fakeredis.FakeServer) -> None:
    expires_at = time.time() + 60
    jti = uuid.uuid4().hex

    first = await RedisTicketStore(_client(server)).consume(jti, expires_at=expires_at)
    replay_elsewhere = await RedisTicketStore(_client(server)).consume(jti, expires_at=expires_at)

    assert (first, replay_elsewhere) == (True, False)
    ttl = await _client(server).pttl(f"teranga:ws-ticket:{jti}")
    assert 0 < ttl <= 60_000


# ------------------------------------------------------------ diffusion (bus)


async def test_an_event_published_on_one_instance_reaches_the_others(
    server: fakeredis.FakeServer,
) -> None:
    received: dict[str, list[tuple[tuple[uuid.UUID, ...], dict[str, Any]]]] = {"a": [], "b": []}

    def deliver(name: str) -> redis_backend.LocalDelivery:
        async def _deliver(recipients: tuple[uuid.UUID, ...], event: dict[str, Any]) -> None:
            received[name].append((recipients, event))

        return _deliver

    bus_a = RedisRealtimeBus(_client(server), deliver("a"))
    bus_b = RedisRealtimeBus(_client(server), deliver("b"))
    listeners = [asyncio.create_task(bus_a.run()), asyncio.create_task(bus_b.run())]
    try:
        await asyncio.sleep(0.2)  # abonnements établis
        user = uuid.uuid4()
        await bus_a.publish((user,), {"type": "message.created", "message": {"id": "m1"}})
        for _ in range(50):
            if received["a"] and received["b"]:
                break
            await asyncio.sleep(0.05)
    finally:
        for task in listeners:
            task.cancel()
        await asyncio.gather(*listeners, return_exceptions=True)

    expected = ((user,), {"type": "message.created", "message": {"id": "m1"}})
    assert received == {"a": [expected], "b": [expected]}


async def test_a_redis_outage_never_breaks_a_message_send() -> None:
    class BrokenClient:
        async def publish(self, *_: object) -> int:
            raise ConnectionError("Redis indisponible")

    async def never(*_: object) -> None:
        raise AssertionError("aucune livraison attendue")

    bus = RedisRealtimeBus(BrokenClient(), never)  # type: ignore[arg-type]
    await bus.publish((uuid.uuid4(),), {"type": "message.created"})  # ne lève pas


async def test_a_malformed_bus_message_is_ignored() -> None:
    delivered: list[object] = []

    async def deliver(*args: object) -> None:
        delivered.append(args)

    bus = RedisRealtimeBus(None, deliver)  # type: ignore[arg-type]
    await bus.handle("pas du json")
    await bus.handle('{"to": ["pas-un-uuid"], "event": {}}')
    assert delivered == []


# ----------------------------------------------------------- cycle de vie


async def test_lifespan_switches_to_redis_then_back_to_memory(fake_redis: None) -> None:
    async with realtime_over_redis(REDIS_URL):
        assert isinstance(realtime_bus(), RedisRealtimeBus)
        assert isinstance(ticket_store(), RedisTicketStore)
    assert isinstance(realtime_bus(), LocalRealtimeBus)
    assert isinstance(ticket_store(), WsTicketRegistry)

    async with realtime_over_redis(None):
        assert isinstance(realtime_bus(), LocalRealtimeBus)
