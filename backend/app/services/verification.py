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

    latest_by_type: dict[VerificationDocType, Verification] = {}
    for verification in verifications:
        current = latest_by_type.get(verification.doc_type)
        if current is None or verification.created_at > current.created_at:
            latest_by_type[verification.doc_type] = verification

    statuses = [latest_by_type.get(doc_type) for doc_type in required_doc_types]

    if all(v is not None and v.status is VerificationStatus.APPROVED for v in statuses):
        return ArtisanVerifiedStatus.VERIFIED

    if any(v is None or v.status is VerificationStatus.PENDING for v in statuses):
        return ArtisanVerifiedStatus.PENDING

    return ArtisanVerifiedStatus.REJECTED
