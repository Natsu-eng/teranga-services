import uuid
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement, WKTElement
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ServiceRequestStatus, Urgency
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.messaging import Conversation
    from app.models.trade import Trade
    from app.models.user import User


class ServiceRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Demande d'un client — le point d'entrée de l'entonnoir."""

    __tablename__ = "service_request"
    __table_args__ = (
        CheckConstraint("ai_estimate_min_fcfa >= 0", name="ai_estimate_min_fcfa_gte_0"),
        CheckConstraint("ai_estimate_max_fcfa >= 0", name="ai_estimate_max_fcfa_gte_0"),
        Index("ix_service_request_location", "location", postgresql_using="gist"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text)
    location: Mapped[WKBElement | WKTElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    urgency: Mapped[Urgency] = mapped_column(
        enum_column(Urgency, "service_request_urgency"), nullable=False, default=Urgency.NORMAL
    )
    ai_estimate_min_fcfa: Mapped[int | None] = mapped_column(Integer)
    ai_estimate_max_fcfa: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ServiceRequestStatus] = mapped_column(
        enum_column(ServiceRequestStatus, "service_request_status"),
        nullable=False,
        default=ServiceRequestStatus.OUVERTE,
        index=True,
    )

    client: Mapped["User"] = relationship(back_populates="service_requests")
    trade: Mapped["Trade"] = relationship()
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="service_request")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="service_request")
