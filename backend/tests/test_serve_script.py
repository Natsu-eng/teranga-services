"""Point d'entrée de production sans pré-déploiement (`scripts/serve.py`,
Render) : configuration validée d'abord, port lu dans `$PORT`, migrations
sous verrou consultatif, puis uvicorn -- jamais dans un autre ordre.

Les migrations réelles ne sont pas relancées ici (elles toucheraient la base
de dev) : `upgrade` est remplacé par une fonction qui OBSERVE l'état du
verrou depuis une autre connexion, ce qui prouve qu'il est bien tenu
pendant la migration et libéré après, même en cas d'échec.
"""

import asyncio
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import config as config_module
from app.core.config import Settings, get_settings
from scripts import serve

BACKEND = Path(__file__).resolve().parent.parent


def _lock_is_free() -> bool:
    """Vrai si le verrou des migrations est libre, vu d'une AUTRE connexion
    (pris puis rendu aussitôt s'il l'est)."""

    async def _probe() -> bool:
        engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                acquired = (
                    await conn.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": serve.MIGRATION_LOCK_KEY}
                    )
                ).scalar_one()
                if acquired:
                    await conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"), {"k": serve.MIGRATION_LOCK_KEY}
                    )
                return bool(acquired)
        finally:
            await engine.dispose()

    return asyncio.run(_probe())


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.exec_argv: list[str] | None = None
        self.lock_free_during_upgrade: bool | None = None

    def upgrade(self) -> None:
        self.events.append("migrations")
        self.lock_free_during_upgrade = _lock_is_free()

    def failing_upgrade(self) -> None:
        self.events.append("migrations")
        raise serve.StartupError("Migrations en échec (simulé).")

    def exec_server(self, path: str, argv: list[str]) -> None:
        self.events.append("uvicorn")
        self.exec_argv = argv


# ------------------------------------------------------------------ port


@pytest.mark.parametrize(
    ("raw", "port"), [(None, 8000), ("", 8000), ("  ", 8000), ("10000", 10000)]
)
def test_port_comes_from_env_with_a_sane_default(raw: str | None, port: int) -> None:
    assert serve.resolve_port(raw) == port


@pytest.mark.parametrize("raw", ["abc", "80.5", "0", "65536", "-1"])
def test_invalid_port_is_refused_never_guessed(raw: str) -> None:
    with pytest.raises(serve.StartupError, match="PORT"):
        serve.resolve_port(raw)


def test_uvicorn_listens_on_all_interfaces_on_the_given_port() -> None:
    argv = serve.uvicorn_argv(10000)
    assert argv[1:4] == ["-m", "uvicorn", "app.main:app"]
    assert argv[argv.index("--host") + 1] == "0.0.0.0"
    assert argv[argv.index("--port") + 1] == "10000"


def test_uvicorn_options_match_the_dockerfile_cmd() -> None:
    """Render (serve.py) et Railway (CMD du Dockerfile) servent l'app à
    l'identique : mêmes options, même port par défaut."""
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    cmd = re.search(r"^CMD \[(.*)\]$", dockerfile, re.MULTILINE)
    assert cmd is not None
    assert "app.main:app --host 0.0.0.0" in cmd.group(1)
    assert f"${{PORT:-{serve.DEFAULT_PORT}}}" in cmd.group(1)
    assert " ".join(serve.UVICORN_OPTIONS) in cmd.group(1)


# ------------------------------------------------------------ démarrage


@pytest.fixture
def fresh_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_startup_order_config_then_locked_migrations_then_uvicorn_on_port() -> None:
    recorder = _Recorder()

    serve.main({"PORT": "10000"}, exec_server=recorder.exec_server, upgrade=recorder.upgrade)

    assert recorder.events == ["migrations", "uvicorn"]
    # Verrou tenu PENDANT la migration (une autre instance attendrait)...
    assert recorder.lock_free_during_upgrade is False
    # ... et rendu après.
    assert _lock_is_free()
    assert recorder.exec_argv is not None
    assert recorder.exec_argv[recorder.exec_argv.index("--port") + 1] == "10000"


def test_failed_migration_stops_startup_and_releases_the_lock() -> None:
    recorder = _Recorder()

    with pytest.raises(SystemExit) as exc:
        serve.main({}, exec_server=recorder.exec_server, upgrade=recorder.failing_upgrade)

    assert "Migrations en échec" in str(exc.value.code)
    assert recorder.events == ["migrations"]  # uvicorn jamais lancé
    assert _lock_is_free()


def test_invalid_port_stops_startup_before_any_migration() -> None:
    recorder = _Recorder()

    with pytest.raises(SystemExit, match="PORT invalide"):
        serve.main({"PORT": "http"}, exec_server=recorder.exec_server, upgrade=recorder.upgrade)

    assert recorder.events == []


@pytest.mark.usefixtures("fresh_settings_cache")
def test_missing_secret_stops_startup_cleanly_before_touching_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration de production incomplète : refus net, liste lisible,
    aucune migration, aucune valeur secrète recopiée dans le message."""
    weak_secret = "change_me_secret_de_test_tres_long_0123456789"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", weak_secret)
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: Settings(_env_file=None),
    )
    recorder = _Recorder()

    with pytest.raises(SystemExit) as exc:
        serve.main({}, exec_server=recorder.exec_server, upgrade=recorder.upgrade)

    message = str(exc.value.code)
    assert message.startswith("Configuration invalide, démarrage refusé :")
    assert "DATABASE_URL : Field required" in message
    assert weak_secret not in message
    assert recorder.events == []


def test_alembic_upgrade_runs_the_railway_command_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(args: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd))
        return subprocess.CompletedProcess(args, returncode=calls.__len__() - 1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    serve.alembic_upgrade_head()  # code 0 : succès silencieux
    with pytest.raises(serve.StartupError, match="code 1"):
        serve.alembic_upgrade_head()

    args, cwd = calls[0]
    assert args[1:] == ["-m", "alembic", "upgrade", "head"]
    assert cwd == BACKEND
