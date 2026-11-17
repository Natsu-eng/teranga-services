"""Réglages des notifications push (VAPID) et clés -- app/core/config.py,
app/core/vapid.py, scripts/generate_vapid_keys.py.

Aucune clé écrite en dur : chaque test génère sa propre paire.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.vapid import (
    b64url_decode,
    b64url_encode,
    generate_key_pair,
    load_private_key,
    load_public_key,
    public_key_matches,
)
from tests.test_production_settings import PRODUCTION
from tests.test_termii import TERMII

BACKEND_DIR = Path(__file__).resolve().parents[1]
SUBJECT = "mailto:contact@teranga.example"


def _push(**overrides: object) -> dict[str, object]:
    public_key, private_key = generate_key_pair()
    return {
        "web_push_enabled": True,
        "vapid_public_key": public_key,
        "vapid_private_key": private_key,
        "vapid_subject": SUBJECT,
        **overrides,
    }


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "jwt_secret": "x" * 32,
        "payment_provider": "disabled",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


# ------------------------------------------------------------------ clés


def test_generated_pair_has_the_web_push_format() -> None:
    public_key, private_key = generate_key_pair()
    assert len(b64url_decode(public_key)) == 65 and b64url_decode(public_key)[0] == 0x04
    assert len(b64url_decode(private_key)) == 32
    assert "=" not in public_key + private_key  # base64url SANS remplissage
    assert public_key_matches(public_key, private_key)


def test_two_different_pairs_do_not_match() -> None:
    public_a, _ = generate_key_pair()
    _, private_b = generate_key_pair()
    assert not public_key_matches(public_a, private_b)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "pas+du/base64url",  # alphabet base64 standard : refusé
        b64url_encode(b"\x04" + b"\x00" * 10),  # trop court
        b64url_encode(b"\x02" + b"\x01" * 64),  # préfixe compressé
        b64url_encode(b"\x04" + b"\x01" * 64),  # hors de la courbe
    ],
)
def test_invalid_public_keys_are_refused(value: str) -> None:
    with pytest.raises(ValueError):
        load_public_key(value)


@pytest.mark.parametrize("value", [b64url_encode(b"\x00" * 32), b64url_encode(b"\x01" * 31), "a b"])
def test_invalid_private_keys_are_refused(value: str) -> None:
    with pytest.raises(ValueError):
        load_private_key(value)


def test_the_script_prints_a_coherent_pair_and_writes_nothing() -> None:
    before = set(BACKEND_DIR.iterdir())
    result = subprocess.run(
        [sys.executable, "scripts/generate_vapid_keys.py"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if not line.startswith("#")
    )
    assert public_key_matches(lines["VAPID_PUBLIC_KEY"], lines["VAPID_PRIVATE_KEY"])
    assert set(BACKEND_DIR.iterdir()) == before


# --------------------------------------------------------- configuration


def test_push_is_disabled_by_default_and_needs_no_key() -> None:
    settings = _settings()
    assert settings.web_push_enabled is False
    assert settings.vapid_private_key is None


def test_enabled_push_accepts_a_coherent_pair_and_cleans_pasted_values() -> None:
    push = _push()
    pasted = {**push, "vapid_private_key": f" {push['vapid_private_key']}\r\n"}
    settings = _settings(**pasted)
    assert settings.vapid_private_key == push["vapid_private_key"]


def test_enabled_push_without_keys_lists_every_missing_setting() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(web_push_enabled=True)
    assert "VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT" in str(exc.value)


def test_a_mismatched_pair_is_refused_without_showing_the_private_key() -> None:
    _, other_private = generate_key_pair()
    with pytest.raises(ValidationError) as exc:
        _settings(**_push(vapid_private_key=other_private))
    assert "ne correspond pas" in str(exc.value)
    assert other_private not in str(exc.value)


def test_an_invalid_private_key_is_refused_without_being_shown() -> None:
    broken = b64url_encode(b"\x00" * 32)
    with pytest.raises(ValidationError) as exc:
        _settings(**_push(vapid_private_key=broken))
    assert "VAPID_PRIVATE_KEY invalide (valeur non affichée)" in str(exc.value)
    assert broken not in str(exc.value)


@pytest.mark.parametrize(
    "subject", ["contact@teranga.example", "mailto:pas-une-adresse", "http://x.sn"]
)
def test_the_subject_must_be_mailto_or_https(subject: str) -> None:
    with pytest.raises(ValidationError, match="VAPID_SUBJECT invalide"):
        _settings(**_push(vapid_subject=subject))


def test_https_subject_is_accepted() -> None:
    assert _settings(**_push(vapid_subject="https://teranga.sn")).vapid_subject


def test_allowed_hosts_are_parsed_from_a_comma_list() -> None:
    settings = _settings(
        **_push(), web_push_allowed_endpoint_hosts=" FCM.googleapis.com, .push.apple.com "
    )
    assert settings.web_push_allowed_endpoint_hosts == ["fcm.googleapis.com", "push.apple.com"]


def test_an_empty_host_list_is_refused() -> None:
    with pytest.raises(ValidationError, match="WEB_PUSH_ALLOWED_ENDPOINT_HOSTS est vide"):
        _settings(**_push(), web_push_allowed_endpoint_hosts="")


def test_production_refuses_push_enabled_without_keys() -> None:
    production = {**PRODUCTION, **TERMII}
    assert Settings(_env_file=None, **production, **_push()).web_push_enabled  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="WEB_PUSH_ENABLED=true mais à renseigner"):
        Settings(_env_file=None, **production, web_push_enabled=True)  # type: ignore[arg-type]
