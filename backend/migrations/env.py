import asyncio
from collections.abc import MutableMapping
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401  -- peuple Base.metadata pour l'autogenerate
from app.core.config import get_settings
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL vient toujours de Settings (backend/.env), jamais d'une
# valeur en dur dans alembic.ini — c'est la même source de vérité que
# l'application, donc les migrations tournent exactement contre la base
# à laquelle l'app se connecterait.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Tables internes posées par `CREATE EXTENSION postgis` : ni déclarées dans
# Base.metadata, ni gérées par nous. Sans ce filtre, l'autogenerate les
# détecte comme "à supprimer" à chaque exécution (faux positif récurrent
# avec PostGIS + Alembic).
_POSTGIS_MANAGED_TABLES = {"spatial_ref_sys"}


_NameType = Literal[
    "schema", "table", "column", "index", "unique_constraint", "foreign_key_constraint"
]


def include_name(
    name: str | None,
    type_: _NameType,
    parent_names: MutableMapping[
        Literal["schema_name", "table_name", "schema_qualified_table_name"], str | None
    ],
) -> bool:
    return not (type_ == "table" and name in _POSTGIS_MANAGED_TABLES)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_name=include_name
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
