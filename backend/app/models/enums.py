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
    EN_ATTENTE = "en_attente"
    REUSSI = "reussi"
    ECHOUE = "echoue"
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


class ReviewStatus(StrEnum):
    PUBLIE = "publie"
    MASQUE = "masque"
    SIGNALE = "signale"


class MessageKind(StrEnum):
    TEXTE = "texte"
    DEVIS = "devis"
    SYSTEME = "systeme"
