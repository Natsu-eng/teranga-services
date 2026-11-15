"""Dérivation de `verified_status` depuis les lignes `verification`.

`artisan_profile.verified_status` n'est **jamais** saisi librement
(BUILD_PLAN.md §2.2, §6 Lot 9) : `compute_verified_status` est la seule
source de vérité, appelée par la couche de lecture (qui charge les
`verification` en eager load et calcule à la volée, sans faire confiance à
la colonne stockée) et par `scripts/seed.py` pour que la colonne reste
cohérente avec ce qu'elle représente.
"""

from collections.abc import Sequence

from app.models.artisan import Verification
from app.models.enums import ArtisanVerifiedStatus, VerificationDocType, VerificationStatus


def compute_verified_status(
    verifications: Sequence[Verification],
    required_doc_types: Sequence[VerificationDocType],
) -> ArtisanVerifiedStatus:
    """Règle exacte (validée avec l'utilisateur, BUILD_PLAN.md §2.2) :

    1. Aucune ligne `verification` du tout -> NONE.
    2. Pour chaque type requis, on ne retient que la ligne la plus récente
       (`created_at` max) -- un artisan peut resoumettre après un rejet.
    3. Tous les types requis ont leur dernière ligne à APPROVED -> VERIFIED.
    4. Sinon, au moins un type requis est absent (rien soumis) ou PENDING
       -> PENDING.
    5. Sinon (au moins un type requis REJECTED, rien en attente) -> REJECTED.
    """
    if not verifications:
        return ArtisanVerifiedStatus.NONE

    statuses = _latest_required(verifications, required_doc_types)

    if all(v is not None and v.status is VerificationStatus.APPROVED for v in statuses):
        return ArtisanVerifiedStatus.VERIFIED

    if any(v is None or v.status is VerificationStatus.PENDING for v in statuses):
        return ArtisanVerifiedStatus.PENDING

    return ArtisanVerifiedStatus.REJECTED


def _latest_required(
    verifications: Sequence[Verification],
    required_doc_types: Sequence[VerificationDocType],
) -> list[Verification | None]:
    """Pour chaque type requis, la ligne la plus récente (`None` si absent)."""
    latest_by_type: dict[VerificationDocType, Verification] = {}
    for verification in verifications:
        current = latest_by_type.get(verification.doc_type)
        if current is None or verification.created_at > current.created_at:
            latest_by_type[verification.doc_type] = verification
    return [latest_by_type.get(doc_type) for doc_type in required_doc_types]


def is_awaiting_review(
    verifications: Sequence[Verification],
    required_doc_types: Sequence[VerificationDocType],
) -> bool:
    """Vrai si le dossier est COMPLET et attend un admin : chaque type requis
    a sa dernière ligne en attente ou déjà approuvée (aucun manquant, aucun
    refusé), et au moins une est en attente.

    Plus strict que `compute_verified_status() == PENDING`, qui vaut aussi
    pour un dossier INCOMPLET (un seul document envoyé) : c'est le passage à
    cet état qui déclenche la notification des admins -- jamais sur un
    dossier partiel, jamais deux fois pour le même passage.
    """
    statuses = _latest_required(verifications, required_doc_types)
    if any(v is None or v.status is VerificationStatus.REJECTED for v in statuses):
        return False
    return any(v is not None and v.status is VerificationStatus.PENDING for v in statuses)
