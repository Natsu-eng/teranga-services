import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
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


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Un encaissement. Le canal inclut le cash — sinon on ne mesure pas la
    fuite hors plateforme (BUILD_PLAN.md §7).

    Ne disparaît jamais en cascade : `intervention_id` est en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),)

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
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    # Idempotence : Wave retente jusqu'à 5x sur 24h avec le même event id.
    wave_event_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    intervention: Mapped["Intervention"] = relationship(back_populates="payments")


class PlatformFee(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Ce que Téranga prélève, découplé du paiement : permet abonnement, lead
    OU commission sans refonte.

    Ne disparaît jamais en cascade : `intervention_id` est en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "platform_fee"
    __table_args__ = (CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),)

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

    intervention: Mapped["Intervention | None"] = relationship(back_populates="platform_fees")
    commission_rate: Mapped["CommissionRate | None"] = relationship(back_populates="platform_fees")


class Payout(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Versement à l'artisan. Le versement rapide est le meilleur rempart
    anti-cash (BUILD_PLAN.md §7).

    Ne disparaît jamais en cascade : `artisan_id`/`intervention_id` sont en
    `ON DELETE RESTRICT`, pas `CASCADE` (données financières).
    """

    __tablename__ = "payout"
    __table_args__ = (CheckConstraint("amount_fcfa >= 0", name="amount_fcfa_gte_0"),)

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
        index=True,
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
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="payouts")
    intervention: Mapped["Intervention"] = relationship(back_populates="payouts")
