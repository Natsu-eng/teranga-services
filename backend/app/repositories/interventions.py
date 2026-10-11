"""Accès données pour `intervention` (BUILD_PLAN.md §3.2, §6 Lot 12).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(validation, autorisation) -- voir `app.services.interventions` pour ça.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.artisan import ArtisanProfile
from app.models.commission import CommissionRate
from app.models.intervention import Intervention
from app.models.request import ServiceRequest
from app.models.review import Review


async def request_has_intervention_for_artisan_user(
    session: AsyncSession, *, request_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Vrai si `user_id` est l'artisan d'au moins une intervention liée à
    `request_id` -- l'artisan est alors "concerné" par cette demande
    (`GET /requests/{id}`, BUILD_PLAN.md §6 Lot 12)."""
    stmt = (
        select(Intervention.id)
        .join(ArtisanProfile, ArtisanProfile.id == Intervention.artisan_id)
        .where(Intervention.service_request_id == request_id, ArtisanProfile.user_id == user_id)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


def _eager_load(
    stmt: Select[tuple[Intervention]],
) -> Select[tuple[Intervention]]:
    return stmt.options(
        joinedload(Intervention.service_request).joinedload(ServiceRequest.trade),
        joinedload(Intervention.artisan).joinedload(ArtisanProfile.user),
        joinedload(Intervention.commission_rate),
        joinedload(Intervention.quote),
        joinedload(Intervention.review).joinedload(Review.author),
        # Fil de discussion (identifiant exposé dans InterventionOut) : une
        # seule requête groupée pour toute la liste, jamais une par ligne.
        selectinload(Intervention.conversations),
        # Paiements, commission, versement, litige : le résumé financier de
        # chaque intervention (BUILD_PLAN.md §3.5), chargé par lots.
        selectinload(Intervention.payments),
        selectinload(Intervention.platform_fees),
        selectinload(Intervention.payouts),
        selectinload(Intervention.dispute),
    )


async def create_intervention(
    session: AsyncSession,
    *,
    service_request: ServiceRequest,
    client_id: uuid.UUID,
    artisan: ArtisanProfile,
    commission_rate: CommissionRate,
) -> Intervention:
    # `service_request=`/`artisan=`/`commission_rate=` (pas leurs `_id`) :
    # peuple les relations en mémoire immédiatement à partir des entités déjà
    # chargées par l'appelant (avec `trade`/`user` eager-loadés) -- la sortie
    # API peut les lire sans requête supplémentaire ni lazy load hors
    # contexte async. `quote=None`/`review=None` explicites : une intervention
    # neuve ne peut avoir ni l'un ni l'autre, mais sans cette affectation
    # explicite ces deux attributs restent "non chargés" et un premier accès
    # après flush (ex. `to_intervention_out`) déclencherait un lazy load hors
    # contexte async (MissingGreenlet) au lieu de lire `None` directement.
    intervention = Intervention(
        service_request=service_request,
        client_id=client_id,
        artisan=artisan,
        commission_rate=commission_rate,
        quote=None,
        review=None,
        # Idem pour le fil de discussion : la conversation créée juste après
        # (même transaction) s'y ajoute en mémoire, sans lazy load.
        conversations=[],
        # Volet financier vide à la création, lu sans requête (même raison).
        payments=[],
        platform_fees=[],
        payouts=[],
        dispute=None,
    )
    session.add(intervention)
    await session.flush()
    return intervention


async def get_by_id(
    session: AsyncSession, intervention_id: uuid.UUID, *, fresh: bool = False
) -> Intervention | None:
    """`fresh` : relit l'état en base même si l'intervention est déjà en
    mémoire (après une écriture faite par une autre transaction)."""
    stmt = _eager_load(select(Intervention).where(Intervention.id == intervention_id))
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def get_by_id_for_update(
    session: AsyncSession, intervention_id: uuid.UUID
) -> Intervention | None:
    """Comme `get_by_id`, en verrouillant la ligne (`SELECT ... FOR UPDATE`)
    jusqu'à la fin de la transaction : toute opération financière sur une
    intervention (paiement, webhook, complétion, annulation, litige) passe
    par ce verrou, donc s'exécute l'une après l'autre -- jamais deux
    décisions concurrentes sur le même séquestre. `populate_existing` :
    l'état relu sous verrou remplace celui déjà en mémoire."""
    stmt = (
        _eager_load(select(Intervention).where(Intervention.id == intervention_id))
        .with_for_update(of=Intervention)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def list_by_ids(
    session: AsyncSession, intervention_ids: list[uuid.UUID]
) -> list[Intervention]:
    """Les interventions demandées, dans l'ordre de `intervention_ids`, avec
    leur client (nom affiché dans l'historique des gains)."""
    if not intervention_ids:
        return []
    stmt = _eager_load(select(Intervention).where(Intervention.id.in_(intervention_ids))).options(
        joinedload(Intervention.client)
    )
    found = {i.id: i for i in (await session.execute(stmt)).unique().scalars().all()}
    return [found[i] for i in intervention_ids if i in found]


async def list_for_client(
    session: AsyncSession, client_id: uuid.UUID, *, limit: int, offset: int
) -> list[Intervention]:
    stmt = _eager_load(select(Intervention).where(Intervention.client_id == client_id))
    stmt = (
        stmt.order_by(Intervention.created_at.desc(), Intervention.id).limit(limit).offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_for_client(session: AsyncSession, client_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Intervention).where(Intervention.client_id == client_id)
    return (await session.execute(stmt)).scalar_one()


async def list_for_artisan(
    session: AsyncSession, artisan_id: uuid.UUID, *, limit: int, offset: int
) -> list[Intervention]:
    stmt = _eager_load(select(Intervention).where(Intervention.artisan_id == artisan_id))
    stmt = (
        stmt.order_by(Intervention.created_at.desc(), Intervention.id).limit(limit).offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_for_artisan(session: AsyncSession, artisan_id: uuid.UUID) -> int:
    stmt = (
        select(func.count()).select_from(Intervention).where(Intervention.artisan_id == artisan_id)
    )
    return (await session.execute(stmt)).scalar_one()
