from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# Fabrique de sessions « à la demande » : `async with factory() as session`.
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


def get_session_factory() -> SessionFactory:
    """Pour les connexions LONGUES (WebSocket) : une session est ouverte le
    temps d'une opération précise (authentification), jamais pendant toute
    la durée de la connexion -- sinon chaque WebSocket ouvert immobiliserait
    une connexion du pool Postgres. Surchargée dans les tests pour réutiliser
    la session transactionnelle de la fixture."""
    return async_session_maker
