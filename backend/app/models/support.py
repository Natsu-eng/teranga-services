import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Role, SupportCategory, SupportTicketStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.user import User

# Bornes de saisie (schémas d'entrée) : une demande d'aide s'explique en
# quelques phrases ; au-delà, un corps démesuré n'est jamais accepté.
SUPPORT_MESSAGE_MIN_LENGTH = 10
SUPPORT_MESSAGE_MAX_LENGTH = 2000
SUPPORT_REPLY_MIN_LENGTH = 3
SUPPORT_REPLY_MAX_LENGTH = 2000


class SupportTicket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Demande d'aide d'un client ou d'un artisan (« Aide / Signaler un
    problème », Profil), traitée par un admin.

    - `message` : enregistré TEL QU'ÉCRIT (non masqué) -- lu seulement par son
      auteur et par les admins, jamais par l'autre partie d'une intervention.
      Il ne figure ni dans l'e-mail aux admins ni dans le journal d'audit.
    - `intervention_id` : facultatif ; s'il est donné, l'intervention
      appartient à l'auteur (client ou artisan), vérifié par le service.
    - Réponse de l'admin (`admin_reply`, `replied_by_id`, `replied_at`) :
      renseignée d'un bloc (CHECK) ; résolution (`resolved_at`) seulement
      avec le statut `resolu` (CHECK). Chaque réponse est journalisée.
    """

    __tablename__ = "support_ticket"
    __table_args__ = (
        CheckConstraint(
            "(admin_reply IS NULL) = (replied_at IS NULL)"
            " AND (admin_reply IS NULL) = (replied_by_id IS NULL)",
            name="reply_fields_together",
        ),
        CheckConstraint(
            "(status = 'resolu') = (resolved_at IS NOT NULL)",
            name="resolved_at_matches_status",
        ),
        # « Mes demandes » (plus récentes d'abord) et file admin par statut.
        Index("ix_support_ticket_author_created", "author_id", "created_at"),
        Index("ix_support_ticket_status_created", "status", "created_at"),
    )

    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # Rôle de l'auteur AU MOMENT de la demande (client ou artisan).
    author_role: Mapped[Role] = mapped_column(
        enum_column(Role, "support_ticket_author_role"), nullable=False
    )
    category: Mapped[SupportCategory] = mapped_column(
        enum_column(SupportCategory, "support_ticket_category"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    intervention_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intervention.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[SupportTicketStatus] = mapped_column(
        enum_column(SupportTicketStatus, "support_ticket_status"),
        nullable=False,
        default=SupportTicketStatus.OUVERT,
    )
    admin_reply: Mapped[str | None] = mapped_column(Text)
    replied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT")
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped["User"] = relationship(foreign_keys=[author_id])
    intervention: Mapped["Intervention | None"] = relationship()
