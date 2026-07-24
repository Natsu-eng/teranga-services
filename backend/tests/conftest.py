"""Fixtures partagées des tests.

`db_session` ouvre une connexion réelle contre la base de dev (`teranga`,
`DATABASE_URL`) dans une transaction jamais commitée : les contraintes
Postgres réelles (CHECK, UNIQUE, EXCLUDE, trigger) sont exercées pour de
vrai, mais tout est annulé en fin de test (`rollback`), y compris si le
test lève une exception. Pas de base de test séparée à provisionner -- la
base de dev n'est jamais polluée.

Moteur dédié en `NullPool` : pytest-asyncio (mode auto) ouvre une nouvelle
boucle asyncio par test, alors que le moteur applicatif (`app.db.session`)
est un singleton importé une fois. Une connexion asyncpg est liée à la
boucle sur laquelle elle a été créée -- la réutiliser depuis un pool entre
deux tests (donc deux boucles) plante. `NullPool` ouvre une connexion neuve
à chaque `connect()` et la ferme pour de bon ensuite, donc aucune n'est
jamais recyclée d'une boucle vers une autre.

Savepoint auto-redémarré : plusieurs tests provoquent volontairement une
violation de contrainte (CHECK, UNIQUE, EXCLUDE, trigger) pour vérifier
qu'elle est bien rejetée. Ce genre d'échec clôt la transaction Postgres en
cours ; sans le savepoint imbriqué relancé à chaque fin de transaction
(recette documentée par SQLAlchemy pour les suites de tests), le rollback
externe final se retrouverait déassocié de la connexion.
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_test_engine = create_async_engine(get_settings().database_url, poolclass=NullPool)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_engine.connect() as conn:
        await conn.begin()
        await conn.begin_nested()
        # expire_on_commit=False : miroir de app.db.session.async_session_maker.
        # Sans ça, un endpoint qui commit puis sérialise l'objet ORM (ex.
        # verify-otp -> UserOut.model_validate(user)) plante avec
        # MissingGreenlet -- l'expiration post-commit déclencherait un
        # rechargement lazy hors contexte async.
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

        @event.listens_for(session.sync_session, "after_transaction_end")
        def _restart_savepoint(sync_session: Session, transaction: object) -> None:
            if conn.closed:
                return
            if not conn.sync_connection.in_nested_transaction():  # type: ignore[union-attr]
                conn.sync_connection.begin_nested()  # type: ignore[union-attr]

        try:
            yield session
        finally:
            await session.close()
            await _rollback_outer(conn)


async def _rollback_outer(conn: AsyncConnection) -> None:
    if not conn.closed and conn.in_transaction():
        await conn.rollback()
