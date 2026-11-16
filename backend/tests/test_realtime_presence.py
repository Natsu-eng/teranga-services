"""Présence « fil ouvert » (app/services/realtime.py, redis_backend.py).

Sert seulement à ne PAS envoyer de notification push pour un message déjà
à l'écran. Contrat vérifié ici : signalement par connexion, effacement,
expiration, isolation par utilisateur, partage entre instances via Redis,
et échec OUVERT (dans le doute : « fil non ouvert », donc notification).
"""

import uuid
from collections.abc import Iterator

import fakeredis
import pytest

from app.services import redis_backend
from app.services.realtime import LocalViewingPresence, viewing_presence
from app.services.redis_backend import RedisViewingPresence, realtime_over_redis

TTL = 60.0
REDIS_URL = "redis://redis.test:6379/0"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def _redis(server: fakeredis.FakeServer) -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)


def _local(clock: FakeClock) -> LocalViewingPresence:
    return LocalViewingPresence(clock=clock)


def _shared(server: fakeredis.FakeServer, clock: FakeClock) -> RedisViewingPresence:
    return RedisViewingPresence(_redis(server), clock=clock)


@pytest.fixture(params=["local", "redis"])
def presence(
    request: pytest.FixtureRequest, server: fakeredis.FakeServer, clock: FakeClock
) -> LocalViewingPresence | RedisViewingPresence:
    return _local(clock) if request.param == "local" else _shared(server, clock)


# --------------------------------------------------- contrat commun


async def test_set_then_clear(presence: LocalViewingPresence | RedisViewingPresence) -> None:
    user, conversation = uuid.uuid4(), uuid.uuid4()
    await presence.set_viewing(user, "c1", conversation, ttl_seconds=TTL)
    assert await presence.is_viewing(user, conversation)
    assert not await presence.is_viewing(user, uuid.uuid4())
    assert not await presence.is_viewing(uuid.uuid4(), conversation)

    await presence.set_viewing(user, "c1", None, ttl_seconds=TTL)
    assert not await presence.is_viewing(user, conversation)


async def test_each_connection_counts_separately(
    presence: LocalViewingPresence | RedisViewingPresence,
) -> None:
    user, conversation = uuid.uuid4(), uuid.uuid4()
    await presence.set_viewing(user, "onglet-1", conversation, ttl_seconds=TTL)
    await presence.set_viewing(user, "onglet-2", conversation, ttl_seconds=TTL)
    await presence.set_viewing(user, "onglet-1", None, ttl_seconds=TTL)
    # L'autre onglet affiche toujours le fil.
    assert await presence.is_viewing(user, conversation)


async def test_a_signal_expires_unless_renewed(
    presence: LocalViewingPresence | RedisViewingPresence, clock: FakeClock
) -> None:
    user, conversation = uuid.uuid4(), uuid.uuid4()
    await presence.set_viewing(user, "c1", conversation, ttl_seconds=TTL)
    clock.now += TTL - 1
    await presence.set_viewing(user, "c1", conversation, ttl_seconds=TTL)  # renouvelé
    clock.now += TTL - 1
    assert await presence.is_viewing(user, conversation)
    clock.now += 2
    # Connexion disparue sans fermeture propre : ne bloque plus les notifications.
    assert not await presence.is_viewing(user, conversation)


# --------------------------------------------------------------- Redis


async def test_redis_presence_is_shared_between_instances(
    server: fakeredis.FakeServer, clock: FakeClock
) -> None:
    user, conversation = uuid.uuid4(), uuid.uuid4()
    await _shared(server, clock).set_viewing(user, "c1", conversation, ttl_seconds=TTL)
    assert await _shared(server, clock).is_viewing(user, conversation)


async def test_redis_keys_never_contain_the_user_id(
    server: fakeredis.FakeServer, clock: FakeClock
) -> None:
    user = uuid.uuid4()
    await _shared(server, clock).set_viewing(user, "c1", uuid.uuid4(), ttl_seconds=TTL)
    keys = await _redis(server).keys("*")
    assert keys and all(str(user) not in key and user.hex not in key for key in keys)


async def test_redis_key_expires_with_the_last_signal(
    server: fakeredis.FakeServer, clock: FakeClock
) -> None:
    await _shared(server, clock).set_viewing(uuid.uuid4(), "c1", uuid.uuid4(), ttl_seconds=TTL)
    (key,) = await _redis(server).keys("*")
    assert 0 < await _redis(server).pttl(key) <= TTL * 1000


async def test_redis_expired_fields_are_purged_on_read(
    server: fakeredis.FakeServer, clock: FakeClock
) -> None:
    user, conversation = uuid.uuid4(), uuid.uuid4()
    presence = _shared(server, clock)
    await presence.set_viewing(user, "ancienne", conversation, ttl_seconds=1)
    await presence.set_viewing(user, "actuelle", uuid.uuid4(), ttl_seconds=TTL)
    clock.now += 2
    assert not await presence.is_viewing(user, conversation)
    (key,) = await _redis(server).keys("*")
    assert list((await _redis(server).hgetall(key)).keys()) == ["actuelle"]


class BrokenRedis:
    """Redis injoignable : toute commande échoue."""

    def __getattr__(self, name: str) -> object:
        raise ConnectionError("Redis injoignable")


async def test_redis_failure_fails_open(caplog: pytest.LogCaptureFixture) -> None:
    presence = RedisViewingPresence(BrokenRedis())  # type: ignore[arg-type]
    user, conversation = uuid.uuid4(), uuid.uuid4()
    await presence.set_viewing(user, "c1", conversation, ttl_seconds=TTL)  # ne lève rien
    # Dans le doute : « fil non ouvert », la notification part.
    assert await presence.is_viewing(user, conversation) is False
    assert "notification envoyée" in caplog.text


@pytest.fixture
def fake_redis(server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(redis_backend, "get_redis_client", lambda _url: _redis(server))
    yield


async def test_lifespan_switches_presence_to_redis_then_back(fake_redis: None) -> None:
    async with realtime_over_redis(REDIS_URL):
        assert isinstance(viewing_presence(), RedisViewingPresence)
    assert isinstance(viewing_presence(), LocalViewingPresence)
