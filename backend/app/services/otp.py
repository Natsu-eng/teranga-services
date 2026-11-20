"""Service OTP : génération, hachage, persistance, envoi et vérification.

Exigences de sécurité (BUILD_PLAN.md §4) :
- code jamais stocké en clair : HMAC-SHA256 salé, avec une clé SECRÈTE
  (`OTP_HMAC_KEY`) gardée hors de la base -- une fuite de la table seule ne
  permet plus de retrouver les codes, et le calcul est instantané (l'ancien
  PBKDF2 à 600 000 itérations bloquait la boucle asynchrone ~1 s par appel) ;
- comparaison en temps constant (`hmac.compare_digest`), jamais `==` ;
- usage unique (`consumed_at`), consommation ATOMIQUE ;
- TTL court, compteur `attempts` incrémenté ATOMIQUEMENT AVANT la
  comparaison : N requêtes simultanées ne donnent jamais plus de
  OTP_MAX_ATTEMPTS essais pour un même code ;
- un nouveau code invalide tous les codes non consommés du même numéro.

Codes PBKDF2 émis avant ce changement : plus acceptés (refusés comme
expirés, l'utilisateur redemande un code) -- ils ne vivent que
OTP_TTL_SECONDS (5 minutes par défaut), l'effet se limite au déploiement.
"""

import hashlib
import hmac
import logging
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.models.otp import OtpCode
from app.services.otp_test_mode import staging_test_code_for
from app.services.sms import SmsProvider, get_sms_provider

logger = logging.getLogger(__name__)

_HASH_ALGO = "hmac_sha256"
_SALT_BYTES = 16
# Clé de repli pour le SEUL poste de développement (et les tests) sans
# OTP_HMAC_KEY : aléatoire, propre au processus, jamais écrite nulle part.
# Hors development/test, la configuration exige OTP_HMAC_KEY au démarrage.
_LOCAL_FALLBACK_KEY = secrets.token_bytes(32)


class OtpInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(code="OTP_INVALIDE", message="Code invalide.", status_code=400)


class OtpExpireError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="OTP_EXPIRE",
            message="Ce code a expiré, merci d'en demander un nouveau.",
            status_code=400,
        )


class OtpDejaUtiliseError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="OTP_DEJA_UTILISE",
            message="Ce code a déjà été utilisé, merci d'en demander un nouveau.",
            status_code=400,
        )


class OtpTropTentativesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="OTP_TROP_TENTATIVES",
            message="Trop de tentatives, merci de demander un nouveau code.",
            status_code=400,
        )


class OtpIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="OTP_INTROUVABLE",
            message="Aucun code en attente pour ce numéro, merci d'en demander un nouveau.",
            status_code=400,
        )


def generate_code(length: int) -> str:
    """Génère un code numérique via `secrets` (jamais `random`)."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def otp_hmac_key(settings: Settings) -> bytes:
    """Clé du hachage : OTP_HMAC_KEY, ou la clé de repli du poste de
    développement. Hors poste local sans clé : refus (déjà bloqué au
    démarrage par `validate_deployed_environment`, défense en profondeur)."""
    if settings.otp_hmac_key:
        return settings.otp_hmac_key.encode("utf-8")
    if not settings.is_local:
        raise RuntimeError("OTP_HMAC_KEY manquante hors poste de développement.")
    return _LOCAL_FALLBACK_KEY


def _digest(code: str, salt: bytes, key: bytes) -> str:
    return hmac.new(key, salt + code.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_code(code: str, *, key: bytes) -> str:
    """HMAC-SHA256 salé : `hmac_sha256$<sel>$<empreinte>` (format
    auto-descriptif, un ancien format est reconnu et refusé)."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return f"{_HASH_ALGO}${salt.hex()}${_digest(code, salt, key)}"


def is_current_hash_format(stored_hash: str) -> bool:
    return stored_hash.startswith(f"{_HASH_ALGO}$")


def verify_code_hash(code: str, stored_hash: str, *, key: bytes) -> bool:
    """Compare en temps constant -- jamais `==` sur un secret. Un hachage
    d'un autre format (ancien PBKDF2) ou malformé ne correspond jamais."""
    try:
        algo, salt_hex, digest_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if algo != _HASH_ALGO:
        return False
    return hmac.compare_digest(_digest(code, salt, key), digest_hex)


async def request_otp(
    session: AsyncSession,
    raw_phone: str,
    *,
    settings: Settings | None = None,
    sms_provider: SmsProvider | None = None,
) -> None:
    """Génère et envoie un nouveau code OTP pour `raw_phone`.

    Aucune branche selon l'existence d'un compte : la table `otp_code` n'a
    pas de FK vers `user` (un OTP peut être demandé pour un numéro sans
    compte -- premier login = création de compte). C'est ce qui rend la
    réponse non énumérante "gratuite" : le chemin d'exécution est identique
    que le compte existe ou non.
    """
    settings = settings or get_settings()
    sms_provider = sms_provider or get_sms_provider(settings)
    phone = normalize_phone(raw_phone, settings)

    now = datetime.now(UTC)
    previous = await session.execute(
        select(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
    )
    for otp in previous.scalars():
        otp.consumed_at = now

    # Mode de test (staging uniquement, numéros listés) : seul le code et sa
    # livraison changent ; hachage, expiration, usage unique et tentatives
    # restent ceux d'un code normal (app/services/otp_test_mode.py).
    test_code = staging_test_code_for(phone, settings)
    code = test_code if test_code is not None else generate_code(settings.otp_code_length)
    otp = OtpCode(
        phone=phone,
        code_hash=hash_code(code, key=otp_hmac_key(settings)),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        attempts=0,
        # Explicite plutôt que le server_default `now()` de la colonne :
        # `now()` renvoie l'heure de *début de transaction* sous Postgres,
        # pas l'heure de l'instruction -- deux OTP émis dans la même
        # transaction (ex. tests) partageraient sinon le même `created_at`,
        # rendant le tri "le plus récent" de `verify_otp` indéterminé.
        created_at=now,
    )
    session.add(otp)
    await session.flush()

    if test_code is not None:
        # Aucun SMS : le collaborateur connaît le code de test. Journalisé
        # sans le numéro ni le code (rien de rejouable dans les journaux).
        logger.info("[staging] code OTP de test émis pour un numéro de la liste de test.")
        return
    await sms_provider.send_otp(phone, code)


async def verify_otp(
    session: AsyncSession,
    raw_phone: str,
    code: str,
    *,
    settings: Settings | None = None,
) -> str:
    """Vérifie `code` pour `raw_phone`. Renvoie le numéro E.164 normalisé si
    valide, lève une `AppError` sinon.
    """
    settings = settings or get_settings()
    phone = normalize_phone(raw_phone, settings)
    now = datetime.now(UTC)

    result = await session.execute(
        select(OtpCode)
        .where(OtpCode.phone == phone)
        # Le code actif (non consommé, s'il y en a un -- il y en a au plus
        # un, `request_otp` invalidant les précédents) passe toujours
        # avant les codes déjà consommés, quel que soit `created_at` :
        # une simple comparaison de dates ne suffit pas à elle seule (deux
        # lignes émises dans la même transaction peuvent partager le même
        # `created_at`, ex. sous le mode savepoint des tests).
        .order_by(OtpCode.consumed_at.is_(None).desc(), OtpCode.created_at.desc())
        .limit(1)
    )
    otp = result.scalar_one_or_none()
    if otp is None:
        raise OtpIntrouvableError()

    if otp.consumed_at is not None:
        raise OtpDejaUtiliseError()

    if otp.expires_at < now:
        raise OtpExpireError()

    if not is_current_hash_format(otp.code_hash):
        # Code émis avant le passage à HMAC (ancien PBKDF2) : plus accepté,
        # consommé et présenté comme expiré -- l'utilisateur en redemande un.
        await _consume(session, otp.id, now=now)
        raise OtpExpireError()

    # RÉSERVE l'essai AVANT toute comparaison, en une seule instruction
    # atomique : sous accès concurrents, PostgreSQL sérialise les UPDATE de
    # la ligne et réévalue la condition -- jamais plus de OTP_MAX_ATTEMPTS
    # essais pour ce code, quel que soit le nombre de requêtes simultanées.
    attempt = (
        await session.execute(
            update(OtpCode)
            .where(
                OtpCode.id == otp.id,
                OtpCode.consumed_at.is_(None),
                OtpCode.attempts < settings.otp_max_attempts,
            )
            .values(attempts=OtpCode.attempts + 1)
            .returning(OtpCode.attempts)
        )
    ).scalar_one_or_none()
    if attempt is None:
        # Essais épuisés, ou code consommé entre-temps par une autre requête :
        # le message dit laquelle des deux (relu en base, pas en mémoire).
        attempts_now = (
            await session.execute(select(OtpCode.attempts).where(OtpCode.id == otp.id))
        ).scalar_one()
        if attempts_now >= settings.otp_max_attempts:
            raise OtpTropTentativesError()
        raise OtpDejaUtiliseError()

    if not verify_code_hash(code, otp.code_hash, key=otp_hmac_key(settings)):
        if attempt >= settings.otp_max_attempts:
            await _consume(session, otp.id, now=now)
            raise OtpTropTentativesError()
        raise OtpInvalideError()

    # Bon code : consommation atomique (une seule requête peut l'emporter).
    if not await _consume(session, otp.id, now=now):
        raise OtpDejaUtiliseError()
    return phone


async def _consume(session: AsyncSession, otp_id: uuid.UUID, *, now: datetime) -> bool:
    """Consomme le code s'il ne l'est pas déjà ; vrai si CETTE requête l'a fait."""
    consumed = (
        await session.execute(
            update(OtpCode)
            .where(OtpCode.id == otp_id, OtpCode.consumed_at.is_(None))
            .values(consumed_at=now)
            .returning(OtpCode.id)
        )
    ).scalar_one_or_none()
    return consumed is not None
