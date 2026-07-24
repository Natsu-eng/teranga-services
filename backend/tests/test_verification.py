"""Règle de dérivation de verified_status (BUILD_PLAN.md §2.2, §6 Lot 9)."""

from datetime import UTC, datetime, timedelta

from app.models.artisan import Verification
from app.models.enums import ArtisanVerifiedStatus, VerificationDocType, VerificationStatus
from app.services.verification import compute_verified_status

REQUIRED = [VerificationDocType.CNI, VerificationDocType.SELFIE]

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _verification(
    doc_type: VerificationDocType,
    status: VerificationStatus,
    *,
    created_at: datetime = _NOW,
) -> Verification:
    return Verification(
        doc_type=doc_type,
        status=status,
        doc_url="https://example.invalid/x.jpg",
        created_at=created_at,
    )


def test_no_verification_at_all_is_none() -> None:
    assert compute_verified_status([], REQUIRED) is ArtisanVerifiedStatus.NONE


def test_all_required_approved_is_verified() -> None:
    verifications = [
        _verification(VerificationDocType.CNI, VerificationStatus.APPROVED),
        _verification(VerificationDocType.SELFIE, VerificationStatus.APPROVED),
    ]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.VERIFIED


def test_extra_non_required_doc_does_not_block_verified() -> None:
    verifications = [
        _verification(VerificationDocType.CNI, VerificationStatus.APPROVED),
        _verification(VerificationDocType.SELFIE, VerificationStatus.APPROVED),
        _verification(VerificationDocType.ACCREDITATION, VerificationStatus.REJECTED),
    ]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.VERIFIED


def test_missing_required_doc_type_is_pending() -> None:
    verifications = [_verification(VerificationDocType.CNI, VerificationStatus.APPROVED)]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.PENDING


def test_required_doc_pending_is_pending() -> None:
    verifications = [
        _verification(VerificationDocType.CNI, VerificationStatus.APPROVED),
        _verification(VerificationDocType.SELFIE, VerificationStatus.PENDING),
    ]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.PENDING


def test_required_doc_rejected_with_nothing_pending_is_rejected() -> None:
    verifications = [
        _verification(VerificationDocType.CNI, VerificationStatus.APPROVED),
        _verification(VerificationDocType.SELFIE, VerificationStatus.REJECTED),
    ]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.REJECTED


def test_missing_takes_precedence_over_rejected() -> None:
    # SELFIE jamais soumis (absent), CNI rejeté : "absent" est prioritaire sur
    # "rejeté" dans la règle -> PENDING (vérification toujours en cours côté
    # SELFIE), pas REJECTED.
    verifications = [_verification(VerificationDocType.CNI, VerificationStatus.REJECTED)]
    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.PENDING


def test_resubmission_after_rejection_uses_latest_row() -> None:
    older_rejected = _verification(
        VerificationDocType.CNI, VerificationStatus.REJECTED, created_at=_NOW
    )
    newer_approved = _verification(
        VerificationDocType.CNI, VerificationStatus.APPROVED, created_at=_NOW + timedelta(days=1)
    )
    selfie = _verification(VerificationDocType.SELFIE, VerificationStatus.APPROVED)

    verifications = [older_rejected, newer_approved, selfie]

    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.VERIFIED


def test_resubmission_that_regresses_uses_latest_row_too() -> None:
    older_approved = _verification(
        VerificationDocType.CNI, VerificationStatus.APPROVED, created_at=_NOW
    )
    newer_pending = _verification(
        VerificationDocType.CNI, VerificationStatus.PENDING, created_at=_NOW + timedelta(days=1)
    )
    selfie = _verification(VerificationDocType.SELFIE, VerificationStatus.APPROVED)

    verifications = [older_approved, newer_pending, selfie]

    assert compute_verified_status(verifications, REQUIRED) is ArtisanVerifiedStatus.PENDING
