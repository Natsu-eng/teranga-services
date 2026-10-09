"""Tests du rate limiting partagé (`PostgresRateLimiter`, table
`rate_limit_hit`) contre la vraie base, et de la sélection du stockage
(`RATE_LIMIT_BACKEND`).

Le limiteur ouvre ses propres connexions et commite (c'est voulu : un appel
décompté doit le rester même si la requête échoue ensuite) -- il ne peut
donc pas vivre dans la transaction annulée de `db_session`. Chaque test
utilise un bucket unique et efface ses lignes à la fin : la base de dev
n'est jamais polluée.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.models.rate_limit import RateLimitHit
from app.services.rate_limit import (
    MAX_WINDOW_SECONDS,
    PostgresRateLimiter,
    SlidingWindowRateLimiter,
    get_otp_rate_limiter,
    hash_rate_limit_key,
)


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    # NullPool : une connexion neuve par opération (voir tests/conftest.py,
    # une connexion asyncpg ne survit pas au changement de boucle entre tests).
    test_engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def bucket(engine: AsyncEngine) -> AsyncGenerator[str, None]:
    name = f"test-{uuid.uuid4().hex[:16]}"
    yield name
    async with engine.begin() as conn:
        await conn.execute(delete(RateLimitHit).where(RateLimitHit.bucket == name))


async def _count(engine: AsyncEngine, bucket: str) -> int:
    async with engine.connect() as conn:
        stmt = select(func.count()).select_from(RateLimitHit).where(RateLimitHit.bucket == bucket)
        return int(await conn.scalar(stmt) or 0)


async def test_allows_up_to_max_then_refuses_without_recording(
    engine: AsyncEngine, bucket: str
) -> None:
    limiter = PostgresRateLimiter(engine, bucket)

    for _ in range(3):
        assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is True
    assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is False

    # Un appel refusé n'est pas décompté : sinon un client qui insiste
    # prolongerait indéfiniment son propre blocage.
    assert await _count(engine, bucket) == 3


async def test_a_new_instance_sees_the_same_counters(engine: AsyncEngine, bucket: str) -> None:
    """Ce que l'état en mémoire ne savait pas faire : une autre instance (ou
    le même service après redémarrage) applique la limite déjà consommée."""
    first_instance = PostgresRateLimiter(engine, bucket)
    for _ in range(2):
        await first_instance.check("ip:203.0.113.7", max_hits=2, window_seconds=60)

    restarted_instance = PostgresRateLimiter(engine, bucket)
    assert await restarted_instance.check("ip:203.0.113.7", max_hits=2, window_seconds=60) is False


async def test_expired_hits_no_longer_count_and_are_purged(
    engine: AsyncEngine, bucket: str
) -> None:
    key = "user:expired"
    old = datetime.now(UTC) - timedelta(seconds=120)
    async with engine.begin() as conn:
        for _ in range(3):
            await conn.execute(
                insert(RateLimitHit).values(
                    bucket=bucket, key_hash=hash_rate_limit_key(bucket, key), hit_at=old
                )
            )

    limiter = PostgresRateLimiter(engine, bucket)
    assert await limiter.check(key, max_hits=3, window_seconds=60) is True
    # Les 3 appels hors fenêtre ont été effacés au passage, reste le nouveau.
    assert await _count(engine, bucket) == 1


async def test_concurrent_checks_never_exceed_the_limit(engine: AsyncEngine, bucket: str) -> None:
    """Le verrou consultatif sérialise les vérifications d'une même clé :
    20 requêtes simultanées pour une limite de 5 n'en laissent passer que 5
    (sans verrou, toutes liraient « 0 appel » en même temps et passeraient)."""
    limiter = PostgresRateLimiter(engine, bucket)

    results = await asyncio.gather(
        *(limiter.check("phone:+221770000000", max_hits=5, window_seconds=60) for _ in range(20))
    )

    assert results.count(True) == 5
    assert await _count(engine, bucket) == 5


async def test_keys_and_buckets_are_isolated(engine: AsyncEngine, bucket: str) -> None:
    limiter = PostgresRateLimiter(engine, bucket)
    assert await limiter.check("user:a", max_hits=1, window_seconds=60) is True
    assert await limiter.check("user:a", max_hits=1, window_seconds=60) is False
    # Autre clé, même bucket : compteur indépendant.
    assert await limiter.check("user:b", max_hits=1, window_seconds=60) is True

    other_bucket = f"{bucket}-other"
    try:
        other = PostgresRateLimiter(engine, other_bucket)
        # Même clé, autre fonctionnalité : compteur indépendant.
        assert await other.check("user:a", max_hits=1, window_seconds=60) is True
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(RateLimitHit).where(RateLimitHit.bucket == other_bucket))


async def test_raw_keys_are_never_stored(engine: AsyncEngine, bucket: str) -> None:
    phone = "+221771112233"
    await PostgresRateLimiter(engine, bucket).check(f"phone:{phone}", max_hits=5, window_seconds=60)

    async with engine.connect() as conn:
        stored = (
            (await conn.execute(select(RateLimitHit.key_hash).where(RateLimitHit.bucket == bucket)))
            .scalars()
            .all()
        )

    assert stored == [hashlib.sha256(f"{bucket}\x00phone:{phone}".encode()).hexdigest()]
    assert all(phone not in value for value in stored)


@pytest.mark.parametrize("limiter_cls", ["memory", "postgres"])
async def test_out_of_range_windows_are_rejected(
    engine: AsyncEngine, bucket: str, limiter_cls: str
) -> None:
    limiter = (
        SlidingWindowRateLimiter()
        if limiter_cls == "memory"
        else PostgresRateLimiter(engine, bucket)
    )
    for window in (0, MAX_WINDOW_SECONDS + 1):
        with pytest.raises(ValueError, match="Fenêtre de rate limiting invalide"):
            await limiter.check("k", max_hits=1, window_seconds=window)


def _settings(**overrides: object) -> Settings:
    base = get_settings().model_dump()
    base.pop("rate_limit_backend")
    return Settings.model_validate({**base, **overrides})


def test_backend_defaults_to_memory_in_dev_and_postgres_elsewhere() -> None:
    assert _settings(app_env="dev").rate_limit_backend == "memory"
    assert _settings(app_env="staging").rate_limit_backend == "postgres"
    assert _settings(app_env="prod").rate_limit_backend == "postgres"


@pytest.mark.parametrize("app_env", ["staging", "prod"])
def test_memory_backend_is_refused_outside_dev(app_env: str) -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_BACKEND=memory est interdit"):
        _settings(app_env=app_env, rate_limit_backend="memory")


def test_dependency_serves_the_configured_storage() -> None:
    assert isinstance(get_otp_rate_limiter(_settings(app_env="dev")), SlidingWindowRateLimiter)
    postgres = get_otp_rate_limiter(_settings(app_env="dev", rate_limit_backend="postgres"))
    assert isinstance(postgres, PostgresRateLimiter)
    # Une seule instance par fonctionnalité et par processus.
    assert postgres is get_otp_rate_limiter(_settings(app_env="prod"))
