"""Enums Python pour toutes les énumérations fermées du modèle de données.

Chaque enum est stocké côté base via `Enum(native_enum=False)` (voir
`app.models.mixins.enum_column`) : une colonne VARCHAR + une contrainte CHECK,
jamais un type PostgreSQL natif (cf. BUILD_PLAN.md §2.2).
"""

from enum import StrEnum


class Role(StrEnum):
    CLIENT = "client"
    ARTISAN = "artisan"
    ADMIN = "admin"


class Locale(StrEnum):
    FR = "fr"
    WO = "wo"


class ArtisanVerifiedStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class SubscriptionTier(StrEnum):
    FREE = "free"
    VERIFIED = "verified"


class VerificationDocType(StrEnum):
    CNI = "cni"
    SELFIE = "selfie"
    ACCREDITATION = "accreditation"
    ADDRESS_PROOF = "address_proof"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Urgency(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"
    IMMEDIAT = "immediat"


class ServiceRequestStatus(StrEnum):
    OUVERTE = "ouverte"
    EN_RELATION = "en_relation"
    CONVERTIE = "convertie"
    ANNULEE = "annulee"
    EXPIREE = "expiree"


class InterventionStatus(StrEnum):
    PROPOSEE = "proposee"
    ACCEPTEE = "acceptee"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"
    ANNULEE = "annulee"
    LITIGE = "litige"


class QuoteStatus(StrEnum):
    PROPOSE = "propose"
    ACCEPTE = "accepte"
    REFUSE = "refuse"
    EXPIRE = "expire"


class PaymentChannel(StrEnum):
    WAVE = "wave"
    ORANGE_MONEY = "orange_money"
    FREE_MONEY = "free_money"
    CARTE = "carte"
    CASH = "cash"


class PaymentStatus(StrEnum):
    """Cycle de vie d'un paiement (BUILD_PLAN.md §3.5).

    En ligne (séquestre) : `en_attente` (checkout ouvert) -> `retenu` (fonds
    reçus et RETENUS par Téranga) -> `libere` (versés à l'artisan à la
    complétion) ou `rembourse` (rendus au client). Un checkout qui n'aboutit
    pas finit `echoue` (refus/expiration chez le fournisseur) ou `annule`
    (abandonné côté Téranga : annulation, changement de moyen de paiement).

    Espèces : `reussi` dès la déclaration -- réglé directement à l'artisan,
    Téranga ne détient jamais ces fonds -- ou `annule` si la mise en relation
    est annulée.
    """

    EN_ATTENTE = "en_attente"
    RETENU = "retenu"
    LIBERE = "libere"
    REUSSI = "reussi"
    ECHOUE = "echoue"
    ANNULE = "annule"
    REMBOURSE = "rembourse"


class PlatformFeeKind(StrEnum):
    COMMISSION = "commission"
    SUBSCRIPTION = "subscription"
    LEAD = "lead"


class PlatformFeeStatus(StrEnum):
    DUE = "due"
    COLLECTEE = "collectee"
    ANNULEE = "annulee"


class PayoutChannel(StrEnum):
    WAVE = "wave"
    ORANGE_MONEY = "orange_money"
    BANK = "bank"


class PayoutStatus(StrEnum):
    EN_ATTENTE = "en_attente"
    ENVOYE = "envoye"
    ECHOUE = "echoue"


class EngagementBlocker(StrEnum):
    """Pourquoi une demande ne peut pas être adressée à un artisan (règle de
    `POST /interventions`, dans cet ordre)."""

    ARTISAN_NON_VERIFIE = "artisan_non_verifie"
    METIER_NON_EXERCE = "metier_non_exerce"
    HORS_ZONE = "hors_zone"


class InterventionCancellationKind(StrEnum):
    """Pourquoi une intervention a fini `annulee`."""

    # L'artisan a décliné la mise en relation avant de l'accepter.
    REFUS = "refus"
    # Une partie y a mis fin en cours de route (avant la complétion).
    ANNULATION = "annulation"
    # Un admin a tranché un litige en faveur du client (remboursement).
    ARBITRAGE = "arbitrage"


class DisputeOutcome(StrEnum):
    """Décision d'un admin sur un litige (BUILD_PLAN.md §3.5)."""

    # Les travaux sont reconnus faits : séquestre libéré à l'artisan.
    LIBERE = "libere"
    # Le client est remboursé, aucune commission.
    REMBOURSE = "rembourse"


class ReviewStatus(StrEnum):
    PUBLIE = "publie"
    MASQUE = "masque"
    SIGNALE = "signale"


class MessageKind(StrEnum):
    TEXTE = "texte"
    DEVIS = "devis"
    SYSTEME = "systeme"
