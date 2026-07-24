import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MessageKind
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.request import ServiceRequest
    from app.models.user import User


class Conversation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Messagerie liée à une demande et/ou une intervention.

    Base pour la détection de fuite hors plateforme (Phase 3+, NLP sur le
    partage de numéros — hors périmètre Phase 2, cf. BUILD_PLAN.md §8).

    `artisan_id` référence `user.id` (et non `artisan_profile.id`, à la
    différence des autres tables) : une conversation se tient entre deux
    comptes utilisateurs, conformément à BUILD_PLAN.md §2.2.
    """

    __tablename__ = "conversation"

    service_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_request.id", ondelete="SET NULL"), index=True
    )
    intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intervention.id", ondelete="SET NULL"), index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    service_request: Mapped["ServiceRequest | None"] = relationship(back_populates="conversations")
    intervention: Mapped["Intervention | None"] = relationship(back_populates="conversations")
    client: Mapped["User"] = relationship(
        back_populates="conversations_as_client", foreign_keys=[client_id]
    )
    artisan_user: Mapped["User"] = relationship(
        back_populates="conversations_as_artisan", foreign_keys=[artisan_id]
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Un message dans une conversation."""

    __tablename__ = "message"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[MessageKind] = mapped_column(
        enum_column(MessageKind, "message_kind"), nullable=False, default=MessageKind.TEXTE
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(back_populates="messages_sent")
