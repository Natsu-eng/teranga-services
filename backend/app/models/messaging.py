import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
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
    """Fil de discussion client ↔ artisan, RATTACHÉ À UNE INTERVENTION
    (BUILD_PLAN.md §3.2, Messagerie) : jamais un canal libre avant
    engagement. Créé dans la même transaction que l'intervention
    (`app.services.interventions.create_intervention`) ; au plus une
    conversation par intervention (index unique partiel).

    `artisan_id` référence `user.id` (et non `artisan_profile.id`, à la
    différence des autres tables) : une conversation se tient entre deux
    comptes utilisateurs, conformément à BUILD_PLAN.md §2.2.

    Non-lus : chaque participant a son curseur de lecture (`*_last_read_seq`,
    le `message.seq` du dernier message qu'il a vu). Un message est non lu
    pour un participant s'il ne l'a pas écrit et que son `seq` dépasse ce
    curseur. Deux colonnes plutôt qu'une table de jointure : une conversation
    a exactement deux participants, fixés à la création.
    """

    __tablename__ = "conversation"
    __table_args__ = (
        # Au plus une conversation par intervention. Partiel : une
        # conversation dont l'intervention serait supprimée (FK SET NULL)
        # garde son historique sans bloquer l'unicité.
        Index(
            "uq_conversation_intervention_id",
            "intervention_id",
            unique=True,
            postgresql_where=text("intervention_id IS NOT NULL"),
        ),
        CheckConstraint("client_last_read_seq >= 0", name="client_last_read_seq_gte_0"),
        CheckConstraint("artisan_last_read_seq >= 0", name="artisan_last_read_seq_gte_0"),
    )

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
    client_last_read_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    artisan_last_read_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # Horodatage du dernier message : tri de la liste par activité récente.
    # Nul tant qu'aucun message n'a été échangé (tri sur `created_at` alors).
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    """Un message dans une conversation : texte, et/ou une image jointe.

    `seq` : numéro d'ordre global strictement croissant, attribué par
    Postgres (identité). C'est le curseur de l'historique et du repli
    polling (`?since=<seq>`) : deux messages peuvent partager un même
    `created_at`, jamais un même `seq`.

    `body` est TOUJOURS la version déjà masquée (numéros de téléphone
    remplacés, `app.services.contact_masking`) : la version d'origine n'est
    jamais persistée. `contact_masked` trace la tentative pour une future
    modération, sans conserver le numéro (minimisation des données).

    Pièce jointe : `attachment_key` est une référence de stockage PRIVÉ
    (jamais une URL publique), servie uniquement aux deux participants par
    un endpoint authentifié, après réencodage (EXIF et position GPS retirés).
    """

    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_conversation_id_seq", "conversation_id", "seq"),
        # Un message porte au moins du texte ou une image, jamais rien.
        CheckConstraint(
            "char_length(body) > 0 OR attachment_key IS NOT NULL", name="body_or_attachment"
        ),
        # Référence et type de la pièce jointe vont toujours ensemble.
        CheckConstraint(
            "(attachment_key IS NULL) = (attachment_content_type IS NULL)",
            name="attachment_complete",
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[MessageKind] = mapped_column(
        enum_column(MessageKind, "message_kind"), nullable=False, default=MessageKind.TEXTE
    )
    contact_masked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    attachment_key: Mapped[str | None] = mapped_column(Text)
    attachment_content_type: Mapped[str | None] = mapped_column(String(64))

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(back_populates="messages_sent")
