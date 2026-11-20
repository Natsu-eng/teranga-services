"""Erreurs métier du moteur de paiement (BUILD_PLAN.md §3.5).

Séparées de `app.services.payments` pour alléger le module ; codes,
messages et statuts HTTP inchangés.
"""

from app.core.errors import AppError
from app.models.enums import PlatformFeeStatus

# ------------------------------------------------------------------ erreurs


class CommissionDejaRegleeError(AppError):
    """Décision « en faveur du client » impossible à appliquer telle quelle :
    la commission n'est plus due (déjà prélevée ou déjà annulée). Rien n'est
    modifié ; l'admin traite le cas manuellement."""

    _LABELS = {
        PlatformFeeStatus.COLLECTEE: "déjà prélevée",
        PlatformFeeStatus.ANNULEE: "déjà annulée",
    }

    def __init__(self, status: PlatformFeeStatus) -> None:
        super().__init__(
            code="COMMISSION_DEJA_REGLEE",
            message=(
                f"La commission de cette intervention est {self._LABELS.get(status, status)} : "
                "la décision en faveur du client ne peut pas être appliquée automatiquement. "
                "Rien n'a été modifié ; traitez ce cas manuellement."
            ),
            status_code=409,
        )


class PaiementNonExigibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_NON_EXIGIBLE",
            message="Le paiement s'ouvre une fois le devis accepté, avant la fin des travaux.",
            status_code=409,
        )


class PaiementDejaEffectueError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_DEJA_EFFECTUE",
            message="Cette intervention est déjà réglée.",
            status_code=409,
        )


class MoyenPaiementIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="MOYEN_DE_PAIEMENT_INDISPONIBLE",
            message="Ce moyen de paiement n'est pas disponible pour le moment.",
            status_code=422,
        )


class PaiementEnLigneIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_EN_LIGNE_INDISPONIBLE",
            message=(
                "Le paiement en ligne n'est pas encore disponible : réglez l'artisan en "
                "espèces, en main propre, et déclarez-le ici."
            ),
            status_code=422,
        )


class FournisseurPaiementIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="FOURNISSEUR_PAIEMENT_INDISPONIBLE",
            message="Le service de paiement ne répond pas. Réessayez dans un instant.",
            status_code=502,
        )


class PaiementEnCoursError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_EN_COURS",
            message=(
                "Un paiement en ligne est en cours pour cette intervention : terminez-le "
                "ou attendez son expiration."
            ),
            status_code=409,
        )


class PaiementEnLigneDesactiveError(AppError):
    def __init__(self) -> None:
        super().__init__(code="NOT_FOUND", message="Ressource introuvable.", status_code=404)


class WebhookSignatureInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_SIGNATURE_INVALIDE",
            message="Notification non authentifiée.",
            status_code=401,
        )


class WebhookIllisibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_ILLISIBLE", message="Notification illisible.", status_code=400
        )
