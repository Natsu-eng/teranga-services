"""Compteur de requêtes SQL émises, pour détecter les régressions N+1
(BUILD_PLAN.md §6, Lot 9).

Écoute `before_cursor_execute` sur la connexion synchrone sous-jacente de la
session de test (`tests/conftest.py::db_session`), le temps du bloc `with` --
scope précis à une seule connexion, pas à tout le moteur partagé entre tests.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


@contextmanager
def count_queries(session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    sync_connection = session.bind.sync_connection  # type: ignore[union-attr]

    def _listener(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    event.listen(sync_connection, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(sync_connection, "before_cursor_execute", _listener)
