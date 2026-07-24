"""Service OTP : génération, hachage, persistance, envoi et vérification.

Exigences de sécurité (BUILD_PLAN.md §4) :
- code jamais stocké en clair (PBKDF2-HMAC-SHA256, salé, itérations élevées --
  un hachage rapide type SHA-256 seul serait trivialement bruteforçable hors
  ligne vu la faible entropie d'un code à 6 chiffres) ;
- comparaison en temps constant (`secrets.compare_digest`), jamais `==` ;
- usage unique (`consumed_at`) ;
- TTL court, compteur `attempts` avec seuil ;
- un nouveau code invalide tous les codes non consommés du même numéro.
"""

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.models.otp import OtpCode
from app.services.sms import SmsProvider, get_sms_provider

_HASH_ALGO = "pbkdf2_sha256"


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


def hash_code(code: str, *, iterations: int) -> str:
    """PBKDF2-HMAC-SHA256, salé. Format auto-descriptif : les futurs
    changements de `iterations` n'invalident pas les hachages déjà en base.
    """
    salt = secrets.token_bytes(16)
    derived = _pbkdf2(code, salt, iterations)
    return f"{_HASH_ALGO}${iterations}${salt.hex()}${derived.hex()}"


def verify_code_hash(code: str, stored_hash: str) -> bool:
    """Compare en temps constant -- jamais `==` sur un secret."""
    try:
        algo, iterations_raw, salt_hex, digest_hex = stored_hash.split("$")
    except ValueError:
        return False
    if algo != _HASH_ALGO:
        return False
    derived = _pbkdf2(code, bytes.fromhex(salt_hex), int(iterations_raw))
    return secrets.compare_digest(derived.hex(), digest_hex)


def _pbkdf2(code: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, iterations)


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

    code = generate_code(settings.otp_code_length)
    otp = OtpCode(
        phone=phone,
        code_hash=hash_code(code, iterations=settings.otp_hash_iterations),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        attempts=0,
    )
    session.add(otp)
    await session.flush()

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
        select(OtpCode).where(OtpCode.phone == phone).order_by(OtpCode.created_at.desc()).limit(1)
    )
    otp = result.scalar_one_or_none()
    if otp is None:
        raise OtpIntrouvableError()

    if otp.consumed_at is not None:
        raise OtpDejaUtiliseError()

    if otp.expires_at < now:
        raise OtpExpireError()

    if otp.attempts >= settings.otp_max_attempts:
        # Défensif : ce cas ne devrait pas se produire (le code est
        # consommé dès que le seuil est atteint, ci-dessous), mais on
        # refuse quand même explicitement si l'invariant est violé.
        otp.consumed_at = now
        await session.flush()
        raise OtpTropTentativesError()

    if not verify_code_hash(code, otp.code_hash):
        otp.attempts += 1
        if otp.attempts >= settings.otp_max_attempts:
            otp.consumed_at = now
            await session.flush()
            raise OtpTropTentativesError()
        await session.flush()
        raise OtpInvalideError()

    otp.consumed_at = now
    await session.flush()
    return phone
