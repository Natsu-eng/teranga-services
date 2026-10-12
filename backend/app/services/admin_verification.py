"""Revue admin des documents de vérification artisan (BUILD_PLAN.md, espace
admin). Approuver/rejeter un document est la SEULE façon dont
`artisan_profile.verified_status` change après le dépôt initial (Lot B) --
toujours via `compute_verified_status`, jamais assigné directement, y
compris ici : un admin ne "rend" pas un artisan vérifié, il approuve des
documents, et c'est la dérivation qui en tire la conséquence.

Accès au binaire des documents : réutilise la même couche de stockage
abstraite que le Lot B (`app.services.storage`), jamais un accès disque
direct ni une URL publique -- seule différence avec `app.services.documents`,
un admin peut lire N'IMPORTE QUEL document (pas seulement les siens).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import AuditAction, AuditTargetType, InterventionStatus, VerificationStatus
from app.models.intervention import Intervention
from app.models.user import User
from app.repositories import audit as audit_repository
from app.repositories import verification as verification_repository
from app.schemas.admin import (
    AdminArtisanDetailOut,
    AdminVerificationListItemOut,
    VerificationReviewOut,
)
from app.schemas.artisans import VerificationDocumentOut
from app.schemas.audit import AuditEntryOut
from app.schemas.pagination import Page
from app.services import audit as audit_service
from app.services.artisans import PageHorsBornesError, get_artisan_or_404, to_detail
from app.services.file_validation import DetectedFileType, detect_file_type
from app.services.storage import StorageBackend, StorageObjectIntrouvableError
from app.services.verification import compute_verified_status


class VerificationIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="VERIFICATION_NOT_FOUND", message="Document introuvable.", status_code=404
        )


class VerificationDejaTraiteeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="VERIFICATION_DEJA_TRAITEE",
            message="Ce document a déjà été traité (approuvé ou rejeté).",
            status_code=409,
        )


async def list_pending_verifications(
    session: AsyncSession,
    *,
    status: VerificationStatus | None,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AdminVerificationListItemOut]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    verifications = await verification_repository.list_by_status(
        session, status=status, limit=resolved_page_size, offset=offset
    )
    total = await verification_repository.count_by_status(session, status=status)

    items = [
        AdminVerificationListItemOut(
            id=v.id,
            artisan_id=v.artisan_id,
            artisan_full_name=v.artisan.user.full_name,
            doc_type=v.doc_type,
            status=v.status,
            note=v.note,
            created_at=v.created_at,
            reviewed_at=v.reviewed_at,
        )
        for v in verifications
    ]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)


async def get_verification_content(
    session: AsyncSession, *, verification_id: uuid.UUID, storage: StorageBackend
) -> tuple[bytes, DetectedFileType]:
    verification = await verification_repository.get_by_id(session, verification_id)
    if verification is None:
        raise VerificationIntrouvableError()

    try:
        content = await storage.retrieve(verification.doc_url)
    except StorageObjectIntrouvableError as exc:
        raise VerificationIntrouvableError() from exc

    detected = detect_file_type(content)
    if detected is None:
        # Ne devrait jamais arriver (le contenu a été validé à l'upload,
        # Lot B) -- filet de sécurité plutôt qu'une 500 non normalisée.
        raise VerificationIntrouvableError()
    return content, detected


async def _review(
    session: AsyncSession,
    *,
    admin: User,
    verification_id: uuid.UUID,
    to_status: VerificationStatus,
    note: str | None,
    settings: Settings,
) -> VerificationReviewOut:
    verification = await verification_repository.get_by_id(session, verification_id)
    if verification is None:
        raise VerificationIntrouvableError()
    if verification.status is not VerificationStatus.PENDING:
        # Un document déjà tranché ne se re-tranche pas : évite qu'un admin
        # approuve/rejette par erreur une ligne devenue obsolète (l'artisan
        # a pu déjà renvoyer un nouveau document du même type après un
        # rejet -- seule la ligne la plus récente compte pour
        # `compute_verified_status`, BUILD_PLAN.md §2.2).
        raise VerificationDejaTraiteeError()

    verification.status = to_status
    verification.note = note
    verification.reviewed_by = admin.id
    verification.reviewed_at = datetime.now(UTC)
    await session.flush()

    artisan = await get_artisan_or_404(session, verification.artisan_id)
    required = list(settings.verification_required_doc_types)
    artisan.verified_status = compute_verified_status(artisan.verifications, required)
    await session.flush()
    # Même transaction que la décision : journalisée si et seulement si validée.
    await audit_service.record(
        session,
        actor=admin,
        action=(
            AuditAction.VERIFICATION_APPROVE
            if to_status is VerificationStatus.APPROVED
            else AuditAction.VERIFICATION_REJECT
        ),
        target_type=AuditTargetType.VERIFICATION,
        target_id=verification.id,
        details={
            "artisan_id": artisan.id,
            "doc_type": verification.doc_type,
            "note": note,
            "artisan_verified_status": artisan.verified_status,
        },
    )

    return VerificationReviewOut(
        id=verification.id,
        doc_type=verification.doc_type,
        status=verification.status,
        note=verification.note,
        reviewed_by=admin.id,
        reviewed_at=verification.reviewed_at,
        artisan_id=artisan.id,
        artisan_verified_status=artisan.verified_status,
    )


async def approve_verification(
    session: AsyncSession, *, admin: User, verification_id: uuid.UUID, settings: Settings
) -> VerificationReviewOut:
    return await _review(
        session,
        admin=admin,
        verification_id=verification_id,
        to_status=VerificationStatus.APPROVED,
        note=None,
        settings=settings,
    )


async def reject_verification(
    session: AsyncSession,
    *,
    admin: User,
    verification_id: uuid.UUID,
    note: str,
    settings: Settings,
) -> VerificationReviewOut:
    return await _review(
        session,
        admin=admin,
        verification_id=verification_id,
        to_status=VerificationStatus.REJECTED,
        note=note,
        settings=settings,
    )


async def get_artisan_detail_for_admin(
    session: AsyncSession, artisan_id: uuid.UUID, *, settings: Settings
) -> AdminArtisanDetailOut:
    profile = await get_artisan_or_404(session, artisan_id)
    required_doc_types = list(settings.verification_required_doc_types)
    detail = to_detail(profile, required_doc_types=required_doc_types)
    documents = sorted(profile.verifications, key=lambda v: v.created_at, reverse=True)
    intervention_counts = {
        status.value: int(total)
        for status, total in (
            await session.execute(
                select(Intervention.status, func.count())
                .where(Intervention.artisan_id == profile.id)
                .group_by(Intervention.status)
            )
        ).all()
    }
    history = await audit_repository.list_for_artisan(
        session, profile.id, limit=settings.pagination_page_size_max
    )
    return AdminArtisanDetailOut(
        id=detail.id,
        full_name=detail.full_name,
        bio=detail.bio,
        years_experience=detail.years_experience,
        avatar_url=detail.avatar_url,
        is_available=detail.is_available,
        verified_status=detail.verified_status,
        trades=detail.trades,
        documents=[VerificationDocumentOut.model_validate(v) for v in documents],
        phone=profile.user.phone,
        created_at=profile.created_at,
        rating_avg=float(profile.rating_avg) if profile.rating_avg is not None else None,
        review_count=profile.review_count,
        is_suspended=profile.suspended_at is not None,
        suspended_at=profile.suspended_at,
        suspension_reason=profile.suspension_reason,
        interventions={
            status.value: intervention_counts.get(status.value, 0) for status in InterventionStatus
        },
        history=[AuditEntryOut.model_validate(entry) for entry in history],
    )
