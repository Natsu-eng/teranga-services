"""Scripts d'exploitation lancés depuis un poste contre une base distante
(Render + Supabase, DEPLOYMENT.md §12.6).

- la base visée est affichée avant d'agir, sans jamais le mot de passe ;
- le jeu de DÉMONSTRATION (`scripts/seed.py`) refuse toute base non locale
  et tout environnement autre que development/test : un poste de dev dont
  DATABASE_URL viserait Supabase ne peut pas semer de faux artisans ni de
  faux avis dans la beta.
"""

import asyncio

import pytest

from app.core.config import Settings
from app.db.target import describe_database, is_local_database
from scripts import create_admin
from scripts.seed import demo_seed_refusal

PASSWORD = "S3cr3t-Supabase-9xQ"
SUPABASE_URL = (
    f"postgresql+asyncpg://postgres.abcdefghijklmnop:{PASSWORD}"
    "@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?ssl=require"
)
LOCAL_URL = "postgresql+asyncpg://teranga:motdepasse@localhost:5432/teranga"


def _settings(environment: str, database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret="x" * 32,
        environment=environment,
        payment_provider="disabled",
    )


def test_target_description_never_shows_the_password() -> None:
    described = describe_database(SUPABASE_URL)
    assert described == (
        "aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
        " (utilisateur postgres.abcdefghijklmnop)"
    )
    assert PASSWORD not in described


@pytest.mark.parametrize(
    ("url", "local"),
    [
        (LOCAL_URL, True),
        ("postgresql+asyncpg://u:p@127.0.0.1:5432/db", True),
        ("postgresql+asyncpg://u:p@[::1]:5432/db", True),
        (SUPABASE_URL, False),
        ("postgresql+asyncpg://u:p@db.abcdefghijklmnop.supabase.co:5432/postgres", False),
    ],
)
def test_local_database_detection(url: str, local: bool) -> None:
    assert is_local_database(url) is local


def test_demo_seed_is_allowed_only_on_a_local_dev_database() -> None:
    assert demo_seed_refusal(_settings("development", LOCAL_URL)) is None
    assert demo_seed_refusal(_settings("test", LOCAL_URL)) is None


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_demo_seed_is_refused_outside_development(environment: str) -> None:
    # La production n'est constructible qu'avec sa configuration complète :
    # même réglages, environnement changé après validation.
    settings = _settings("staging", SUPABASE_URL).model_copy(update={"environment": environment})
    refusal = demo_seed_refusal(settings)
    assert refusal is not None
    assert f"ENVIRONMENT={environment}" in refusal


def test_demo_seed_is_refused_against_a_remote_database_even_from_a_dev_machine() -> None:
    """Le piège réel : `.env` de dev (ENVIRONMENT=development) et DATABASE_URL
    exportée vers Supabase pour lancer seed_reference.py."""
    refusal = demo_seed_refusal(_settings("development", SUPABASE_URL))
    assert refusal is not None
    assert "base non locale : aws-0-eu-central-1.pooler.supabase.com" in refusal
    assert PASSWORD not in refusal


def test_create_admin_shows_the_target_database_before_asking(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """La base visée est affichée AVANT la question ; refuser n'ouvre aucune
    connexion."""
    monkeypatch.setattr(
        create_admin, "get_settings", lambda: _settings("development", SUPABASE_URL)
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    exit_code = asyncio.run(create_admin._run("+221771234567", skip_confirmation=False))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output.splitlines()[0] == f"Base visée : {describe_database(SUPABASE_URL)}"
    assert "Annulé." in output
    assert PASSWORD not in output
