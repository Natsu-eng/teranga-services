import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    PaymentChannel,
    PaymentStatus,
    PayoutChannel,
    PayoutStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
)
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.artisan import ArtisanProfile
    from app.models.commission import CommissionRate
    from app.models.intervention import Intervention

# Statuts d'un paiement « vivant » : au plus UN par intervention (index
# partiel `uq_payment_active_intervention_id`). Un checkout abandonné
# (`echoue`/`annule`) ou un remboursement (`rembourse`) libère la place.
ACTIVE_PAYMENT_STATUSES = (
    PaymentStatus.EN_ATTENTE,
    PaymentStatus.RETENU,
    PaymentStatus.LIBERE,
    PaymentStatus.REUSSI,
)


def _sql_in(values: tuple[PaymentStatus, ...]) -> str:
    return ", ".join(f"'{value.value}'" for value in values)


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Un encaissement (BUILD_PLAN.md §3.5). Le canal inclut le cash -- sinon
    on ne mesure pas la fuite hors plateforme (BUILD_PLAN.md §7).

    Le montant est TOUJOURS celui de l'intervention (devis accepté), copié
    par le serveur : jamais une valeur reçue du client.

    Ne disparaît jamais en cascade : `intervention_id` est en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),
        # Le cash ne passe par aucun fournisseur ; tout paiement en ligne en a un.
        CheckConstraint(
            "(channel = 'cash') = (provider IS NULL)", name="provider_iff_online_channel"
        ),
        # Une référence de fournisseur ne désigne qu'un seul paiement : c'est
        # par elle qu'un webhook retrouve le paiement concerné.
        UniqueConstraint("provider", "provider_ref", name="uq_payment_provider_provider_ref"),
        Index(
            "uq_payment_active_intervention_id",
            "intervention_id",
            unique=True,
            postgresql_where=text(f"status IN ({_sql_in(ACTIVE_PAYMENT_STATUSES)})"),
        ),
    )

    intervention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intervention.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[PaymentChannel] = mapped_column(
        enum_column(PaymentChannel, "payment_channel"), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus, "payment_status"),
        nullable=False,
        default=PaymentStatus.EN_ATTENTE,
        index=True,
    )
    # Fournisseur qui a porté le paiement (ex. "sandbox") ; NULL pour le cash.
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    # Page de paiement hébergée par le fournisseur, réutilisée tant qu'elle
    # n'a pas expiré (un double clic ne crée jamais deux checkouts).
    checkout_url: Mapped[str | None] = mapped_column(Text)
    checkout_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Fonds reçus par Téranga (en ligne) ou déclarés remis à l'artisan (cash).
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_ref: Mapped[str | None] = mapped_column(String(255))

    intervention: Mapped["Intervention"] = relationship(back_populates="payments")
    events: Mapped[list["PaymentEvent"]] = relationship(back_populates="payment")


class PaymentEvent(UUIDPrimaryKeyMixin, Base):
    """Journal des notifications (webhooks) reçues des fournisseurs.

    **Clé d'idempotence** : `(provider, event_id)` est unique. Un fournisseur
    retente une même notification plusieurs fois (jusqu'à 24 h) : la
    deuxième insertion échoue sur cette contrainte et l'événement n'est
    JAMAIS retraité -- ni double encaissement, ni double versement.
    Les événements ignorés (paiement inconnu) sont journalisés aussi : un
    rejeu ultérieur reste un no-op, et l'anomalie reste traçable.
    """

    __tablename__ = "payment_event"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_payment_event_provider_event_id"),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id", ondelete="RESTRICT"), index=True
    )
    # Ce que le traitement a fait de l'événement (ex. "retenu", "ignore",
    # "deja_traite", "montant_incoherent") -- lisible lors d'un audit.
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payment: Mapped["Payment | None"] = relationship(back_populates="events")


class PlatformFee(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Ce que Téranga prélève, découplé du paiement : permet abonnement, lead
    OU commission sans refonte.

    Commission (BUILD_PLAN.md §3.5) : une seule par intervention, calculée
    sur le taux FIGÉ de l'intervention. `due` tant qu'elle n'est pas
    prélevée ; `collectee` quand le séquestre est libéré (déduite du
    versement) ; `annulee` si l'intervention est annulée ou remboursée. En
    cash, elle reste `due` : due par l'artisan, recouvrement hors périmètre.

    Ne disparaît jamais en cascade : `intervention_id` est en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "platform_fee"
    __table_args__ = (
        CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),
        Index(
            "uq_platform_fee_commission_intervention_id",
            "intervention_id",
            unique=True,
            postgresql_where=text("kind = 'commission'"),
        ),
    )

    intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intervention.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[PlatformFeeKind] = mapped_column(
        enum_column(PlatformFeeKind, "platform_fee_kind"), nullable=False
    )
    amount_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_rate.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[PlatformFeeStatus] = mapped_column(
        enum_column(PlatformFeeStatus, "platform_fee_status"),
        nullable=False,
        default=PlatformFeeStatus.DUE,
        index=True,
    )
    # Passage à `collectee` ou `annulee`.
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    intervention: Mapped["Intervention | None"] = relationship(back_populates="platform_fees")
    commission_rate: Mapped["CommissionRate | None"] = relationship(back_populates="platform_fees")


class Payout(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Versement à l'artisan. Le versement rapide est le meilleur rempart
    anti-cash (BUILD_PLAN.md §7).

    Un seul par intervention. Toujours vers le numéro VÉRIFIÉ (OTP) du compte
    artisan, copié ici pour l'audit : jamais un numéro saisi à la volée, qui
    permettrait de détourner un versement.

    Ne disparaît jamais en cascade : `artisan_id`/`intervention_id` sont en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "payout"
    __table_args__ = (
        CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),
        CheckConstraint("attempts >= 0", name="attempts_gte_0"),
        UniqueConstraint("intervention_id", name="uq_payout_intervention_id"),
    )

    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artisan_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    intervention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intervention.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[PayoutChannel] = mapped_column(
        enum_column(PayoutChannel, "payout_channel"), nullable=False
    )
    status: Mapped[PayoutStatus] = mapped_column(
        enum_column(PayoutStatus, "payout_status"),
        nullable=False,
        default=PayoutStatus.EN_ATTENTE,
        index=True,
    )
    destination_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="payouts")
    intervention: Mapped["Intervention"] = relationship(back_populates="payouts")
