"""Point d'entrée de production SANS étape de pré-déploiement (Render,
DEPLOYMENT.md §12) : valide la configuration, applique les migrations, puis
démarre uvicorn sur `$PORT`.

Sur Railway, rien ne change : les migrations y passent par
`preDeployCommand` (railway.json) et le conteneur garde le `CMD` du
Dockerfile. Ce script n'est utilisé que là où il est demandé explicitement
(`dockerCommand` de render.yaml).

Étapes, dans cet ordre :

1. **Configuration** : `Settings` est construit AVANT toute action. Un secret
   manquant ou une valeur interdite arrête le démarrage avec la liste des
   problèmes (code de sortie 1), sans toucher à la base.
2. **Port** : `$PORT` fourni par la plateforme ; 8000 s'il est absent ou
   vide. Une valeur invalide arrête le démarrage (jamais d'écoute sur un
   port deviné, que la plateforme ne joindrait pas).
3. **Migrations** : `alembic upgrade head`, idempotent (rien à faire si la
   base est à jour). Exécuté sous un VERROU CONSULTATIF PostgreSQL : si deux
   instances démarrent en même temps, la seconde attend la fin de la
   première puis ne trouve plus rien à appliquer -- jamais deux migrations
   concurrentes. Un échec arrête le démarrage : l'ancienne version reste en
   service (la plateforme ne bascule pas sur une instance qui ne démarre pas).
4. **Serveur** : uvicorn REMPLACE ce processus (`exec`) : il reçoit
   directement les signaux d'arrêt de la plateforme (arrêt gracieux). Mêmes
   options que le `CMD` du Dockerfile (parité vérifiée par les tests).

Usage (image Docker) : `python scripts/serve.py`
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Exécuté comme un script de fichier : backend/ doit être sur sys.path.
sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

DEFAULT_PORT = 8000
# Clé du verrou consultatif des migrations (entier 64 bits fixe, propre à
# Téranga : « teranga1 » en ASCII). Toute instance utilise la même.
MIGRATION_LOCK_KEY = 0x74_65_72_61_6E_67_61_31
# Options d'uvicorn : identiques au CMD du Dockerfile (Railway).
UVICORN_OPTIONS = ("--no-server-header", "--timeout-graceful-shutdown", "20")


class StartupError(Exception):
    """Démarrage refusé : message destiné à l'opérateur (journaux)."""


def resolve_port(raw: str | None) -> int:
    """Port d'écoute depuis `$PORT` ; 8000 si absent ou vide."""
    if raw is None or not raw.strip():
        return DEFAULT_PORT
    try:
        port = int(raw.strip())
    except ValueError:
        raise StartupError(f"PORT invalide : {raw!r} (entier attendu).") from None
    if not 1 <= port <= 65535:
        raise StartupError(f"PORT hors limites : {port} (1 à 65535).")
    return port


def uvicorn_argv(port: int) -> list[str]:
    """Ligne de commande d'uvicorn. `WEB_CONCURRENCY` (nombre de workers)
    est lu par uvicorn lui-même dans l'environnement, comme sur Railway."""
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        *UVICORN_OPTIONS,
    ]


def load_settings_or_fail() -> str:
    """Valide toute la configuration ; renvoie DATABASE_URL."""
    from app.core.config import get_settings

    try:
        return get_settings().database_url
    except ValidationError as exc:
        # Une ligne par problème : nom de la variable (s'il y en a un) et
        # message, JAMAIS la valeur saisie (pas de secret dans les journaux ;
        # la représentation par défaut de pydantic l'inclurait).
        problems = "\n".join(
            "  - " + (f"{str(error['loc'][0]).upper()} : " if error["loc"] else "") + error["msg"]
            for error in exc.errors()
        )
        raise StartupError(f"Configuration invalide, démarrage refusé :\n{problems}") from None


def alembic_upgrade_head() -> None:
    """Exactement la commande du preDeployCommand Railway."""
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=False
    )
    if completed.returncode != 0:
        raise StartupError(
            f"Migrations en échec (alembic upgrade head, code {completed.returncode}) : "
            "démarrage refusé, la version précédente reste en service."
        )


async def migrate_under_lock(database_url: str, upgrade: Callable[[], None]) -> None:
    """Applique `upgrade` en tenant le verrou consultatif des migrations.

    Verrou de SESSION, posé sur une connexion dédiée en autocommit (aucune
    transaction laissée ouverte pendant la migration), libéré même en cas
    d'échec -- et, au pire, par PostgreSQL à la fermeture de la connexion.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as raw_connection:
            connection = await raw_connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
            )
            try:
                # Alembic lance sa propre boucle asyncio : dans un thread à part.
                await asyncio.to_thread(upgrade)
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
                )
    finally:
        await engine.dispose()


def main(
    environ: dict[str, str] | None = None,
    *,
    exec_server: Callable[[str, list[str]], None] = os.execv,
    upgrade: Callable[[], None] = alembic_upgrade_head,
) -> None:
    environ = dict(os.environ) if environ is None else environ
    try:
        database_url = load_settings_or_fail()
        port = resolve_port(environ.get("PORT"))
        print("Migrations : alembic upgrade head (sous verrou)...", flush=True)
        asyncio.run(migrate_under_lock(database_url, upgrade))
    except StartupError as exc:
        sys.exit(str(exc))
    print(f"Migrations à jour. Démarrage d'uvicorn sur 0.0.0.0:{port}.", flush=True)
    argv = uvicorn_argv(port)
    exec_server(argv[0], argv)


if __name__ == "__main__":
    main()
