"""Accès données pour `verification` (documents de vérification artisan,
BUILD_PLAN.md, onboarding artisan). Requêtes SQLAlchemy pures -- jamais de
Pydantic ni de logique métier (validation de type de fichier, autorisation),
voir `app.services.documents` pour ça.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
