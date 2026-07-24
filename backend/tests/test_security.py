import uuid
from datetime import datetime

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    TokenInvalideError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from app.models.enums import Locale, Role
from app.models.user import User


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        phone="+221771234567",
        full_name="Test User",
        role=Role.CLIENT,
        locale=Locale.FR,
    )


def test_access_token_roundtrip() -> None:
    settings = _settings()
    user = _user()

    token = encode_access_token(user, settings=settings)
    payload = decode_token(token, settings=settings)

    assert payload["sub"] == str(user.id)
    assert payload["role"] == "client"
    assert payload["type"] == "access"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)


def test_refresh_token_roundtrip_carries_jti() -> None:
    settings = _settings()
    user = _user()
    jti = uuid.uuid4()

    token = encode_refresh_token(user, jti=jti, settings=settings)
    payload = decode_token(token, settings=settings)

    assert payload["type"] == "refresh"
    assert payload["jti"] == str(jti)


def test_decode_rejects_expired_access_token() -> None:
    settings = _settings(jwt_access_ttl_seconds=-10)
    token = encode_access_token(_user(), settings=settings)

    with pytest.raises(TokenInvalideError):
        decode_token(token, settings=_settings())


def test_decode_rejects_wrong_secret() -> None:
    token = encode_access_token(_user(), settings=_settings(jwt_secret="a" * 32))

    with pytest.raises(TokenInvalideError):
        decode_token(token, settings=_settings(jwt_secret="b" * 32))


def test_decode_rejects_tampered_signature() -> None:
    settings = _settings()
    token = encode_access_token(_user(), settings=settings)

    header, payload, signature = token.split(".")
    # Corrompt un caractère au milieu de la signature (pas le dernier : sur
    # un base64url non paddé, le tout dernier caractère peut avoir des bits
    # "don't care" qui ne changent pas les octets décodés).
    index = len(signature) // 2
    flipped = "A" if signature[index] != "A" else "B"
    tampered = f"{header}.{payload}.{signature[:index]}{flipped}{signature[index + 1 :]}"

    with pytest.raises(TokenInvalideError):
        decode_token(tampered, settings=settings)


def test_jwt_payload_never_leaks_the_raw_secret() -> None:
    settings = _settings()
    token = encode_access_token(_user(), settings=settings)
    # Le payload est lisible sans vérification (JWT n'est pas chiffré) --
    # on vérifie juste qu'aucun champ ne contient jamais le secret lui-même.
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert settings.jwt_secret not in str(unverified)


def test_encode_access_token_uses_settings_ttl() -> None:
    settings = _settings(jwt_access_ttl_seconds=60)
    before = datetime.now().timestamp()
    token = encode_access_token(_user(), settings=settings)
    payload = decode_token(token, settings=settings)

    assert 55 <= payload["exp"] - int(before) <= 65
