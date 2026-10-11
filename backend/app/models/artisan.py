import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement, WKTElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    ArtisanVerifiedStatus,
    PayoutChannel,
    SubscriptionTier,
    VerificationDocType,
    VerificationStatus,
)
from app.models.mixins import (
    CreatedAtMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.payment import Payout
    from app.models.review import Review
    from app.models.trade import Trade
    from app.models.user import User


class ArtisanProfile(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Extension 1:1 d'un `user` de rôle `artisan`."""

    __tablename__ = "artisan_profile"
    __table_args__ = (
        Index("ix_artisan_profile_base_location", "base_location", postgresql_using="gist"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    bio: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[int | None] = mapped_column(Integer)
    base_location: Mapped[WKBElement | WKTElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    avatar_url: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verified_status: Mapped[ArtisanVerifiedStatus] = mapped_column(
        enum_column(ArtisanVerifiedStatus, "artisan_profile_verified_status"),
        nullable=False,
        default=ArtisanVerifiedStatus.NONE,
        index=True,
    )
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        enum_column(SubscriptionTier, "artisan_profile_subscription_tier"),
        nullable=False,
        default=SubscriptionTier.FREE,
    )
    # Dénormalisé depuis `review` (avis `publie` uniquement) : un AVG() par
    # artisan sur chaque requête de liste ne tient pas à l'échelle. Recalculé
    # par `app.services.reviews.recalculate_artisan_rating`, jamais saisi
    # directement (BUILD_PLAN.md §6, Lot 9).
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(precision=3, scale=2))
    # Moyen de versement choisi par l'artisan (BUILD_PLAN.md §3.5). Le numéro,
    # lui, n'est jamais saisi : c'est toujours celui du compte, vérifié par
    # OTP. NULL = réglage par défaut (PAYOUT_DEFAULT_CHANNEL).
    payout_channel: Mapped[PayoutChannel | None] = mapped_column(
        enum_column(PayoutChannel, "artisan_profile_payout_channel")
    )
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped["User"] = relationship(back_populates="artisan_profile")
    verifications: Mapped[list["Verification"]] = relationship(
        back_populates="artisan", cascade="all, delete-orphan", passive_deletes=True
    )
    artisan_trades: Mapped[list["ArtisanTrade"]] = relationship(
        back_populates="artisan", cascade="all, delete-orphan", passive_deletes=True
    )
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="artisan")
    reviews_received: Mapped[list["Review"]] = relationship(back_populates="artisan")
    payouts: Mapped[list["Payout"]] = relationship(back_populates="artisan")


class Verification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Document de vérification d'un artisan (CNI, selfie, accréditation…).

    Plusieurs par artisan, avec statut — inspiré de Checkatrade. Pas de
    `updated_at` : `reviewed_at` porte déjà l'horodatage de la transition.
    """

    __tablename__ = "verification"

    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artisan_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[VerificationDocType] = mapped_column(
        enum_column(VerificationDocType, "verification_doc_type"), nullable=False
    )
    doc_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.PENDING,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="verifications")
    reviewer: Mapped["User | None"] = relationship(
        back_populates="verifications_reviewed", foreign_keys=[reviewed_by]
    )


class ArtisanTrade(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Un métier exercé par un artisan, avec sa zone d'intervention.

    Un artisan peut exercer plusieurs métiers, chacun avec son propre tarif
    et rayon/zone d'intervention.
    """

    __tablename__ = "artisan_trade"
    __table_args__ = (
        CheckConstraint("hourly_rate_fcfa >= 0", name="hourly_rate_fcfa_gte_0"),
        Index("ix_artisan_trade_service_area", "service_area", postgresql_using="gist"),
    )

    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artisan_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    hourly_rate_fcfa: Mapped[int] = mapped_column(Integer, nullable=False)
    service_radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    service_area: Mapped[WKBElement | WKTElement | None] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False)
    )

    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="artisan_trades")
    trade: Mapped["Trade"] = relationship()
