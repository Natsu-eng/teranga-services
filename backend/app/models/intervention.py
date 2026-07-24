import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InterventionStatus, QuoteStatus
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.artisan import ArtisanProfile
    from app.models.commission import CommissionRate
    from app.models.messaging import Conversation
    from app.models.payment import Payment, Payout, PlatformFee
    from app.models.request import ServiceRequest
    from app.models.review import Review
    from app.models.user import User


class Intervention(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Le cœur de l'entonnoir : une mise en relation qui devient un travail
    réel. L'ancre de la commission, des avis et des paiements."""

    __tablename__ = "intervention"
    __table_args__ = (CheckConstraint("agreed_amount_fcfa >= 0", name="agreed_amount_fcfa_gte_0"),)

    service_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_request.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artisan_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[InterventionStatus] = mapped_column(
        enum_column(InterventionStatus, "intervention_status"),
        nullable=False,
        default=InterventionStatus.PROPOSEE,
        index=True,
    )
    # Taux figé à la création : jamais recalculé si commission_rate change ensuite.
    commission_rate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("commission_rate.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agreed_amount_fcfa: Mapped[int | None] = mapped_column(Integer)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_request: Mapped["ServiceRequest"] = relationship(back_populates="interventions")
    client: Mapped["User"] = relationship(back_populates="interventions_as_client")
    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="interventions")
    commission_rate: Mapped["CommissionRate"] = relationship(back_populates="interventions")
    quote: Mapped["Quote | None"] = relationship(
        back_populates="intervention", cascade="all, delete-orphan", passive_deletes=True
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="intervention")
    platform_fees: Mapped[list["PlatformFee"]] = relationship(back_populates="intervention")
    payouts: Mapped[list["Payout"]] = relationship(back_populates="intervention")
    review: Mapped["Review | None"] = relationship(back_populates="intervention")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="intervention")


class Quote(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Devis. 1:1 avec une intervention — le devis accepté la matérialise."""

    __tablename__ = "quote"
    __table_args__ = (
        CheckConstraint("labor_fcfa >= 0", name="labor_fcfa_gte_0"),
        CheckConstraint("materials_fcfa >= 0", name="materials_fcfa_gte_0"),
        CheckConstraint("total_fcfa >= 0", name="total_fcfa_gte_0"),
        CheckConstraint(
            "total_fcfa = labor_fcfa + materials_fcfa", name="total_fcfa_eq_labor_plus_materials"
        ),
    )

    intervention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intervention.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    labor_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    materials_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    total_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(
        enum_column(QuoteStatus, "quote_status"), nullable=False, default=QuoteStatus.PROPOSE
    )

    intervention: Mapped["Intervention"] = relationship(back_populates="quote")
