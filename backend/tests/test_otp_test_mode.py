"""Mode OTP de test de la beta (app/services/otp_test_mode.py).

Deux verrous INDÉPENDANTS le rendent impossible en production, chacun
prouvé ici par son propre test :
1. au démarrage : `Settings` refuse toute configuration de test hors staging ;
2. à l'exécution : même une configuration qui aurait échappé à la
   validation n'a aucun effet hors staging.
Et la liste ne contourne QUE la livraison du SMS : hachage, usage unique,
expiration, tentatives, débit et non-énumération restent les mêmes.
"""

from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import app
from app.models.otp import OtpCode
from app.services import otp as otp_service
from app.services.otp_test_mode import is_test_mode_enabled, staging_test_code_for
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter
from tests.factories import unique_phone

# Code de test propre à cette suite (la vraie valeur de staging est
# configurée par OTP_TEST_CODE, jamais écrite dans le code).
TEST_CODE = "482913"
STRONG_SECRET = "Q2x9mV7pLr4tZb8NwK3sHc6YdF1gJ5uEaT0oRiXy"


class _RecordingSms:
    """Fournisseur SMS simulé : enregistre chaque envoi."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))


def _settings(environment: str = "staging", **overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "environment": environment,
        "payment_provider": "disabled",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def _unvalidated(environment: str, whitelist: list[str], code: str) -> Settings:
    """Réglages construits SANS validation (comme si un verrou de démarrage
    avait été contourné) : sert à prouver le verrou d'exécution seul."""
    valid = _settings("development").model_dump()
    valid.update(environment=environment, otp_test_whitelist=whitelist, otp_test_code=code)
    return Settings.model_construct(**valid)


async def _stored(session: AsyncSession, phone: str) -> OtpCode:
    stored = (
        (
            await session.execute(
                select(OtpCode)
                .where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
                .order_by(OtpCode.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert stored is not None
    return stored


# ----------------------------------------------------- verrou n°1 : démarrage


def test_production_refuses_any_test_configuration() -> None:
    production = {
        "database_url": "postgresql+asyncpg://teranga:S9vR2kLq7ZtW4mPx@db.internal:5432/teranga",
        "jwt_secret": STRONG_SECRET,
        "frontend_public_base_url": "https://teranga.sn",
        "backend_public_base_url": "https://api.teranga.sn",
    }
    for extra in (
        {"otp_test_whitelist": ["+221770000001"], "otp_test_code": TEST_CODE},
        {"otp_test_whitelist": ["+221770000001"]},
        {"otp_test_code": TEST_CODE},
    ):
        with pytest.raises(ValidationError) as exc:
            _settings("production", **production, **extra)
        assert "OTP_TEST_WHITELIST / OTP_TEST_CODE sont interdits en production" in str(exc.value)


@pytest.mark.parametrize("environment", ["development", "test"])
def test_test_mode_is_staging_only_even_locally(environment: str) -> None:
    with pytest.raises(ValidationError, match="ne sont permis qu'avec ENVIRONMENT=staging"):
        _settings(environment, otp_test_whitelist=["+221770000001"], otp_test_code=TEST_CODE)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"otp_test_whitelist": ["+221770000001"]}, "vont ensemble"),
        ({"otp_test_code": TEST_CODE}, "vont ensemble"),
        ({"otp_test_whitelist": ["+221770000001"], "otp_test_code": "12345"}, "6 chiffres"),
        ({"otp_test_whitelist": ["+221770000001"], "otp_test_code": "12a456"}, "6 chiffres"),
        ({"otp_test_whitelist": ["770000001"], "otp_test_code": TEST_CODE}, "E.164"),
        # Non-énumération : un fournisseur qui échoue pour les numéros hors
        # liste (500) les distinguerait des numéros listés (204).
        (
            {
                "otp_test_whitelist": ["+221770000001"],
                "otp_test_code": TEST_CODE,
                "sms_provider": "unconfigured",
            },
            "révéleraient la liste",
        ),
    ],
)
def test_incomplete_or_malformed_test_configuration_is_refused(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings("staging", **overrides)


def test_whitelist_is_read_from_a_comma_separated_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_TEST_WHITELIST", "+221770000001, +221770000002")
    monkeypatch.setenv("OTP_TEST_CODE", TEST_CODE)
    settings = _settings("staging")
    assert settings.otp_test_whitelist == ["+221770000001", "+221770000002"]
    assert is_test_mode_enabled(settings)
    assert not is_test_mode_enabled(_settings("staging", otp_test_whitelist=[], otp_test_code=""))


# --------------------------------------------------- verrou n°2 : exécution


@pytest.mark.parametrize("environment", ["production", "development", "test"])
async def test_outside_staging_a_bypassed_configuration_has_no_effect(
    db_session: AsyncSession, environment: str
) -> None:
    """Même si la validation de démarrage était contournée, hors staging le
    numéro listé suit le flux NORMAL : vrai SMS, code aléatoire, et le code
    de test est refusé."""
    phone = unique_phone()
    settings = _unvalidated(environment, [phone], TEST_CODE)
    assert staging_test_code_for(phone, settings) is None
    assert not is_test_mode_enabled(settings)

    sms = _RecordingSms()
    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)

    assert len(sms.sent) == 1, "le fournisseur SMS doit être appelé hors staging"
    ((_, sent_code),) = sms.sent
    if sent_code == TEST_CODE:  # probabilité 1/10^6 : aucune conclusion possible
        pytest.skip("code aléatoire égal au code de test, par hasard")
    with pytest.raises(otp_service.OtpInvalideError):
        await otp_service.verify_otp(db_session, phone, TEST_CODE, settings=settings)


# ------------------------------------------------- staging : comportement


async def test_staging_whitelisted_number_gets_the_test_code_without_sms(
    db_session: AsyncSession,
) -> None:
    phone = unique_phone()
    settings = _settings(otp_test_whitelist=[phone], otp_test_code=TEST_CODE)
    sms = _RecordingSms()

    await otp_service.request_otp(db_session, phone, settings=settings, sms_provider=sms)

    assert sms.sent == []  # aucun SMS payant
    stored = await _stored(db_session, phone)
    assert TEST_CODE not in stored.code_hash  # toujours haché, jamais en clair
    assert stored.code_hash.startswith("pbkdf2_sha256$")
    assert await otp_service.verify_otp(db_session, phone, TEST_CODE, settings=settings) == phone
    # Usage unique : le même code ne resert pas.
    with pytest.raises(otp_service.OtpDejaUtiliseError):
        await otp_service.verify_otp(db_session, phone, TEST_CODE, settings=settings)


async def test_staging_number_outside_the_list_follows_the_normal_flow(
    db_session: AsyncSession,
) -> None:
    listed, other = unique_phone(), unique_phone()
    settings = _settings(otp_test_whitelist=[listed], otp_test_code=TEST_CODE)
    sms = _RecordingSms()

    await otp_service.request_otp(db_session, other, settings=settings, sms_provider=sms)

    ((sent_phone, sent_code),) = sms.sent
    assert sent_phone == other
    if sent_code == TEST_CODE:
        pytest.skip("code aléatoire égal au code de test, par hasard")
    with pytest.raises(otp_service.OtpInvalideError):
        await otp_service.verify_otp(db_session, other, TEST_CODE, settings=settings)


async def test_test_code_keeps_attempt_limit_and_expiry(db_session: AsyncSession) -> None:
    phone = unique_phone()
    settings = _settings(otp_test_whitelist=[phone], otp_test_code=TEST_CODE)

    # Tentatives : au-delà du seuil, même le bon code est refusé.
    await otp_service.request_otp(
        db_session, phone, settings=settings, sms_provider=_RecordingSms()
    )
    for _ in range(settings.otp_max_attempts - 1):
        with pytest.raises(otp_service.OtpInvalideError):
            await otp_service.verify_otp(db_session, phone, "000000", settings=settings)
    with pytest.raises(otp_service.OtpTropTentativesError):
        await otp_service.verify_otp(db_session, phone, "000000", settings=settings)
    with pytest.raises(otp_service.OtpDejaUtiliseError):
        await otp_service.verify_otp(db_session, phone, TEST_CODE, settings=settings)

    # Expiration : un code de test expiré est refusé comme un autre.
    await otp_service.request_otp(
        db_session, phone, settings=settings, sms_provider=_RecordingSms()
    )
    stored = await _stored(db_session, phone)
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(otp_service.OtpExpireError):
        await otp_service.verify_otp(db_session, phone, TEST_CODE, settings=settings)


# ------------------------------------------- staging : de bout en bout (HTTP)


@pytest.fixture
def staging_app(db_session: AsyncSession) -> Iterator[str]:
    phone = unique_phone()
    settings = get_settings().model_copy(
        update={
            "environment": "staging",
            "otp_test_whitelist": [phone],
            "otp_test_code": TEST_CODE,
        }
    )

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_otp_rate_limiter] = lambda: limiter
    yield phone
    app.dependency_overrides.clear()


async def test_staging_collaborator_signs_up_with_the_test_code(staging_app: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        listed = await http.post("/api/v1/auth/request-otp", json={"phone": staging_app})
        unlisted = await http.post("/api/v1/auth/request-otp", json={"phone": unique_phone()})
        verified = await http.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": staging_app,
                "code": TEST_CODE,
                "intent": "signup",
                "role": "client",
                "full_name": "Awa Testeuse",
            },
        )

    # Non-énumération : réponse identique, numéro listé ou non.
    assert (listed.status_code, listed.content) == (unlisted.status_code, unlisted.content)
    assert listed.status_code == 204
    assert verified.status_code == 200, verified.text
    assert verified.json()["user"]["phone"] == staging_app


async def test_staging_test_numbers_stay_rate_limited(staging_app: str) -> None:
    settings = app.dependency_overrides[get_settings]()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        statuses = [
            (await http.post("/api/v1/auth/request-otp", json={"phone": staging_app})).status_code
            for _ in range(settings.rate_limit_otp_per_phone_max + 1)
        ]
    assert statuses[-1] == 429
    assert set(statuses[:-1]) == {204}
