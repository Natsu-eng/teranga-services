"""Accès données pour `verification` (documents de vérification artisan,
BUILD_PLAN.md, onboarding artisan). Requêtes SQLAlchemy pures -- jamais de
Pydantic ni de logique métier (validation de type de fichier, autorisation),
voir `app.services.documents` pour ça.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.artisan import ArtisanProfile, Verification
from app.models.enums import VerificationDocType, VerificationStatus


async def create_verification(
    session: AsyncSession,
    *,
    artisan: ArtisanProfile,
    doc_type: VerificationDocType,
    doc_url: str,
) -> Verification:
    # `artisan=artisan` (pas `artisan_id=artisan.id`) : peuple la relation
    # `ArtisanProfile.verifications` en mémoire immédiatement (back_populates),
    # indispensable pour que `compute_verified_status` voie ce document sans
    # requête supplémentaire juste après (même pattern que
    # `app.repositories.requests.create_service_request`, `trade=trade`).
    verification = Verification(
        artisan=artisan,
        doc_type=doc_type,
        doc_url=doc_url,
        status=VerificationStatus.PENDING,
    )
    session.add(verification)
    await session.flush()
    return verification


async def get_owned(
    session: AsyncSession, *, verification_id: uuid.UUID, artisan_id: uuid.UUID
) -> Verification | None:
    """Un document, scopé à l'artisan propriétaire -- `None` si absent OU
    s'il appartient à un autre artisan (jamais de distinction observable
    entre les deux depuis l'extérieur, cf. `app.services.documents`)."""
    stmt = select(Verification).where(
        Verification.id == verification_id, Verification.artisan_id == artisan_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_id(session: AsyncSession, verification_id: uuid.UUID) -> Verification | None:
    """Un document, non scopé à un propriétaire -- réservé à l'espace admin
    (`app.services.admin_verification`), jamais exposé à un artisan (voir
    `get_owned` pour l'accès self-service, Lot B)."""
    stmt = select(Verification).where(Verification.id == verification_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_by_status(
    session: AsyncSession, *, status: VerificationStatus | None, limit: int, offset: int
) -> list[Verification]:
    """File d'attente de revue admin, triée du plus ancien au plus récent
    (FIFO) -- un document déposé en premier doit être traité en premier.
    `artisan`/`artisan.user` eager-loadés pour construire
    `AdminVerificationListItemOut.artisan_full_name` sans requête N+1."""
    stmt = (
        select(Verification)
        .options(joinedload(Verification.artisan).joinedload(ArtisanProfile.user))
        .order_by(Verification.created_at.asc(), Verification.id)
    )
    if status is not None:
        stmt = stmt.where(Verification.status == status)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_by_status(session: AsyncSession, *, status: VerificationStatus | None) -> int:
    stmt = select(func.count()).select_from(Verification)
    if status is not None:
        stmt = stmt.where(Verification.status == status)
    return (await session.execute(stmt)).scalar_one()
