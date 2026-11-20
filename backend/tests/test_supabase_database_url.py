"""DATABASE_URL Supabase (DEPLOYMENT.md §12.4) : session pooler, port 5432,
driver asyncpg et TLS exigé ; pooler transaction (6543) refusé.

Pas de réseau : on vérifie que la chaîne documentée est acceptée par
`Settings` et que SQLAlchemy la traduit en paramètres de connexion asyncpg
exacts (hôte, port, utilisateur avec la référence du projet, TLS) -- ceux
qu'utiliseront l'application ET les migrations (migrations/env.py lit la
même DATABASE_URL).
"""

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from tests.deployed_settings import DEPLOYED_REQUIRED

POOLER = "aws-0-eu-central-1.pooler.supabase.com"
SESSION_URL = (
    f"postgresql+asyncpg://postgres.abcdefghijklmnop:mot%40de%3Apasse@{POOLER}:5432/postgres"
    "?ssl=require"
)


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret="x" * 32,
        environment="staging",
        payment_provider="disabled",
        **DEPLOYED_REQUIRED,  # type: ignore[arg-type]
    )


def test_documented_session_pooler_url_is_accepted() -> None:
    assert _settings(SESSION_URL).database_url == SESSION_URL


def test_asyncpg_receives_the_pooler_user_port_and_tls() -> None:
    engine = create_async_engine(SESSION_URL)
    try:
        _, params = engine.dialect.create_connect_args(engine.url)
    finally:
        engine.sync_engine.dispose()

    assert params["host"] == POOLER
    assert params["port"] == 5432
    assert params["user"] == "postgres.abcdefghijklmnop"
    # Mot de passe encodé dans l'URL, décodé pour le driver.
    assert params["password"] == "mot@de:passe"
    assert params["database"] == "postgres"
    assert params["ssl"] == "require"


def test_transaction_pooler_is_refused_with_an_explanation() -> None:
    with pytest.raises(ValidationError, match="pooler TRANSACTION de Supabase"):
        _settings(SESSION_URL.replace(":5432/", ":6543/"))


@pytest.mark.parametrize(
    "url",
    [
        # Le port 6543 n'est refusé que sur le pooler Supabase.
        "postgresql+asyncpg://u:p@db.example.com:6543/app",
        # Base locale de développement : inchangée.
        "postgresql+asyncpg://teranga:motdepasse@localhost:5432/teranga",
    ],
)
def test_other_databases_are_untouched(url: str) -> None:
    assert _settings(url).database_url == url
