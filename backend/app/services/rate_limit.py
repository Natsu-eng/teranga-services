"""Rate limiting à fenêtre glissante (BUILD_PLAN.md §4), trois stockages
interchangeables derrière le même contrat `RateLimiter` :

- `RedisRateLimiter` (app/services/redis_backend.py), dès que `REDIS_URL`
  est renseignée : partagé par toutes les instances, script Lua atomique ;
- `PostgresRateLimiter` (staging/prod sans Redis) : compteurs dans la table
  `rate_limit_hit`, partagés par toutes les instances et persistants -- la
  limite reste la même quel que soit le nombre de workers, et un
  redéploiement ne remet pas les compteurs à zéro.
- `SlidingWindowRateLimiter` (dev, tests) : `dict` en mémoire, local au
  processus.

Le choix se fait par `RATE_LIMIT_BACKEND` (app/core/config.py), qui refuse
"memory" hors dev. Les routes ne dépendent que du contrat, via les
dépendances `get_*_rate_limiter` ci-dessous (que les tests remplacent par
une instance fraîche avec `dependency_overrides`).
"""

import asyncio
import hashlib
import time
from datetime import timedelta
from typing import Annotated, Protocol

from fastapi import Depends
from sqlalchemy import Interval, bindparam, delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.models.rate_limit import RateLimitHit

# Au-delà, une fenêtre n'a plus de sens pour un rate limiting anti-abus, et
# la purge globale (lignes de plus de 24 h) effacerait des appels encore
# décomptés. Toutes les fenêtres configurées aujourd'hui font 10 minutes.
MAX_WINDOW_SECONDS = 24 * 3600

# Purge globale des lignes expirées, au plus une fois par intervalle et par
# processus -- les clés jamais revues (numéro saisi une seule fois...) ne
# restent pas indéfiniment en base.
_GLOBAL_PURGE_INTERVAL_SECONDS = 600


class RateLimiter(Protocol):
    async def check(self, key: str, *, max_hits: int, window_seconds: int) -> bool:
        """Enregistre un appel pour `key` et renvoie `False` (sans le
        décompter) si `max_hits` appels ont déjà eu lieu sur les
        `window_seconds` dernières secondes."""
        ...


def validate_window(window_seconds: int) -> None:
    if not 0 < window_seconds <= MAX_WINDOW_SECONDS:
        raise ValueError(
            f"Fenêtre de rate limiting invalide : {window_seconds} s "
            f"(attendu entre 1 et {MAX_WINDOW_SECONDS})."
        )


class SlidingWindowRateLimiter:
    """Stockage en mémoire, local au processus (dev et tests uniquement)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, *, max_hits: int, window_seconds: int) -> bool:
        validate_window(window_seconds)
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            hits = self._hits.get(key, [])
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if not hits:
                # Purge les clés redevenues inactives -- sans ça, chaque
                # numéro/IP jamais revu resterait en mémoire indéfiniment.
                self._hits.pop(key, None)

            if len(hits) >= max_hits:
                return False

            hits.append(now)
            self._hits[key] = hits
            return True


def hash_rate_limit_key(bucket: str, key: str) -> str:
    """Empreinte stockée à la place de la clé : jamais de numéro de
    téléphone, d'IP ou d'identifiant en clair dans `rate_limit_hit`. Le
    `bucket` est inclus pour qu'une même clé n'ait pas la même empreinte
    d'un limiteur à l'autre."""
    return hashlib.sha256(f"{bucket}\x00{key}".encode()).hexdigest()


class PostgresRateLimiter:
    """Stockage partagé dans `rate_limit_hit` (staging/prod).

    Chaque vérification tourne dans SA PROPRE transaction, sur sa propre
    connexion, commitée immédiatement -- jamais dans la session de la
    requête : un appel refusé ensuite (fichier invalide, code OTP faux...)
    reste décompté, sinon il suffirait d'échouer volontairement pour
    contourner la limite.

    Concurrence : un verrou consultatif transactionnel par (bucket, clé)
    sérialise les vérifications simultanées d'une même clé, y compris
    depuis plusieurs instances -- sans lui, N requêtes parallèles liraient
    toutes « 2 appels sur 3 » et passeraient toutes. Les clés différentes ne
    se bloquent jamais entre elles.

    Base indisponible : l'exception remonte (500), la requête est refusée
    -- échec FERMÉ, jamais une limite levée en silence.
    """

    def __init__(self, engine: AsyncEngine, bucket: str) -> None:
        self._engine = engine
        self._bucket = bucket
        self._last_global_purge = float("-inf")

    async def check(self, key: str, *, max_hits: int, window_seconds: int) -> bool:
        validate_window(window_seconds)
        key_hash = hash_rate_limit_key(self._bucket, key)
        window = bindparam("window", timedelta(seconds=window_seconds), type_=Interval)
        same_key = (RateLimitHit.bucket == self._bucket) & (RateLimitHit.key_hash == key_hash)

        async with self._engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"rate_limit:{key_hash}"},
            )
            await conn.execute(
                delete(RateLimitHit).where(
                    same_key, RateLimitHit.hit_at <= func.clock_timestamp() - window
                )
            )
            count = await conn.scalar(
                select(func.count()).select_from(RateLimitHit).where(same_key)
            )
            allowed = (count or 0) < max_hits
            if allowed:
                await conn.execute(
                    insert(RateLimitHit).values(bucket=self._bucket, key_hash=key_hash)
                )

        await self._maybe_purge_expired()
        return allowed

    async def _maybe_purge_expired(self) -> None:
        now = time.monotonic()
        if now - self._last_global_purge < _GLOBAL_PURGE_INTERVAL_SECONDS:
            return
        self._last_global_purge = now
        horizon = bindparam("horizon", timedelta(seconds=MAX_WINDOW_SECONDS), type_=Interval)
        async with self._engine.begin() as conn:
            await conn.execute(
                delete(RateLimitHit).where(RateLimitHit.hit_at <= func.clock_timestamp() - horizon)
            )


# Un limiteur par fonctionnalité : une même IP ou un même utilisateur ne
# partage jamais son compteur entre deux usages sans rapport.
OTP_BUCKET = "otp"
AI_ANALYZE_BUCKET = "ai_analyze"
DOCUMENT_UPLOAD_BUCKET = "document_upload"
PROFILE_MEDIA_UPLOAD_BUCKET = "profile_media_upload"
MESSAGE_SEND_BUCKET = "message_send"
MESSAGE_ATTACHMENT_BUCKET = "message_attachment"
PAYMENT_INIT_BUCKET = "payment_init"
PUSH_SUBSCRIPTION_BUCKET = "push_subscription"

_memory_limiters: dict[str, SlidingWindowRateLimiter] = {}
_postgres_limiters: dict[str, PostgresRateLimiter] = {}
_redis_limiters: dict[str, RateLimiter] = {}


def _limiter_for(bucket: str, settings: Settings) -> RateLimiter:
    """Instance unique par bucket et par processus, du stockage choisi par
    `RATE_LIMIT_BACKEND` (déjà résolu et validé par `Settings`)."""
    if settings.rate_limit_backend == "redis" and settings.redis_url:
        if bucket not in _redis_limiters:
            from app.services.redis_backend import RedisRateLimiter, get_redis_client

            _redis_limiters[bucket] = RedisRateLimiter(get_redis_client(settings.redis_url), bucket)
        return _redis_limiters[bucket]
    if settings.rate_limit_backend == "postgres":
        if bucket not in _postgres_limiters:
            # Import tardif : le moteur applicatif n'est créé que si le
            # stockage partagé est réellement utilisé.
            from app.db.session import engine

            _postgres_limiters[bucket] = PostgresRateLimiter(engine, bucket)
        return _postgres_limiters[bucket]
    return _memory_limiters.setdefault(bucket, SlidingWindowRateLimiter())


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_otp_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/auth/request-otp` -- clés par numéro et par IP."""
    return _limiter_for(OTP_BUCKET, settings)


def get_ai_analyze_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/ai/analyze` -- clé par IP (endpoint public)."""
    return _limiter_for(AI_ANALYZE_BUCKET, settings)


def get_document_upload_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/artisans/me/documents` -- clé par utilisateur
    authentifié (documents de vérification, régime privé)."""
    return _limiter_for(DOCUMENT_UPLOAD_BUCKET, settings)


def get_profile_media_upload_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/artisans/me/avatar` et `.../me/cover` -- un seul budget
    partagé entre les deux (même clé par utilisateur authentifié)."""
    return _limiter_for(PROFILE_MEDIA_UPLOAD_BUCKET, settings)


def get_message_send_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/conversations/{id}/messages` -- clé par utilisateur
    authentifié, toutes conversations confondues (un script ne peut pas
    contourner la limite en ouvrant plusieurs fils)."""
    return _limiter_for(MESSAGE_SEND_BUCKET, settings)


def get_message_attachment_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/conversations/{id}/messages/image` -- budget distinct,
    plus serré : chaque envoi décode, réencode et écrit un fichier."""
    return _limiter_for(MESSAGE_ATTACHMENT_BUCKET, settings)


def get_payment_init_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST /api/v1/payments/init` -- clé par utilisateur authentifié :
    chaque appel peut ouvrir un checkout chez le fournisseur."""
    return _limiter_for(PAYMENT_INIT_BUCKET, settings)


def get_push_subscription_rate_limiter(settings: SettingsDep) -> RateLimiter:
    """`POST` et `DELETE /api/v1/push/subscriptions` -- un budget partagé,
    clé par utilisateur authentifié (chaque appel écrit en base)."""
    return _limiter_for(PUSH_SUBSCRIPTION_BUCKET, settings)
