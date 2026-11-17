"""Accès aux abonnements Web Push (`push_subscription`)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push import PushSubscription
from app.models.user import User


async def upsert(
    session: AsyncSession, *, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str
) -> None:
    """Enregistre l'abonnement d'un appareil, de façon idempotente.

    `endpoint` déjà connu (même navigateur) : rattaché à `user_id` -- même
    s'il appartenait à un autre compte (appareil partagé, changement de
    compte) -- et ses clés remplacées. Une seule requête atomique : deux
    enregistrements simultanés ne créent jamais de doublon.
    """
    # `clock_timestamp()` (et non `now()`, figé au début de la transaction) :
    # l'ordre « plus récent » reste exact, même en rafale.
    stamp = func.clock_timestamp()
    statement = insert(PushSubscription).values(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        created_at=stamp,
        updated_at=stamp,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={
                "user_id": statement.excluded.user_id,
                "p256dh": statement.excluded.p256dh,
                "auth": statement.excluded.auth,
                "updated_at": stamp,
            },
        )
    )


async def keep_most_recent(session: AsyncSession, *, user_id: uuid.UUID, keep: int) -> int:
    """Oublie les abonnements de `user_id` au-delà des `keep` plus récents ;
    renvoie le nombre supprimé."""
    stale = (
        select(PushSubscription.id)
        .where(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.updated_at.desc(), PushSubscription.id)
        .offset(keep)
    )
    result = await session.execute(
        delete(PushSubscription)
        .where(PushSubscription.id.in_(stale.scalar_subquery()))
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def delete_for_user(session: AsyncSession, *, user_id: uuid.UUID, endpoint: str) -> int:
    """Supprime l'abonnement `endpoint` SEULEMENT s'il appartient à `user_id`."""
    result = await session.execute(
        delete(PushSubscription)
        .where(PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint)
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def list_active_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> Sequence[PushSubscription]:
    """Abonnements d'un compte NON supprimé (jamais de notification vers un
    compte supprimé, même si ses abonnements n'ont pas encore disparu)."""
    result = await session.execute(
        select(PushSubscription)
        .join(User, User.id == PushSubscription.user_id)
        .where(PushSubscription.user_id == user_id, User.deleted_at.is_(None))
        .order_by(PushSubscription.updated_at.desc())
    )
    return result.scalars().all()


async def delete_by_ids(session: AsyncSession, ids: Sequence[uuid.UUID]) -> int:
    if not ids:
        return 0
    result = await session.execute(
        delete(PushSubscription)
        .where(PushSubscription.id.in_(ids))
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)
