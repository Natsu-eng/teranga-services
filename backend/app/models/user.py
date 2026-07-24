from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Locale, Role
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.artisan import ArtisanProfile, Verification
    from app.models.intervention import Intervention
    from app.models.messaging import Conversation, Message
    from app.models.refresh_token import RefreshToken
    from app.models.request import ServiceRequest
    from app.models.review import Review


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Compte de base, commun client et artisan.

    Le rôle vit ici, côté serveur (`role`), contrôlé à chaque requête — plus
    jamais un `userRole` auto-déclarable côté client (BUILD_PLAN.md §1, §4).
    """

    __tablename__ = "user"

    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[Role] = mapped_column(enum_column(Role, "user_role"), nullable=False)
    locale: Mapped[Locale] = mapped_column(
        enum_column(Locale, "user_locale"), nullable=False, default=Locale.FR
    )

    artisan_profile: Mapped["ArtisanProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    verifications_reviewed: Mapped[list["Verification"]] = relationship(back_populates="reviewer")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="client")
    interventions_as_client: Mapped[list["Intervention"]] = relationship(back_populates="client")
    reviews_written: Mapped[list["Review"]] = relationship(back_populates="author")
    conversations_as_client: Mapped[list["Conversation"]] = relationship(
        back_populates="client", foreign_keys="Conversation.client_id"
    )
    conversations_as_artisan: Mapped[list["Conversation"]] = relationship(
        back_populates="artisan_user", foreign_keys="Conversation.artisan_id"
    )
    messages_sent: Mapped[list["Message"]] = relationship(back_populates="sender")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
