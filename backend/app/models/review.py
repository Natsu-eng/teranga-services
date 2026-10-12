import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReviewStatus
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.artisan import ArtisanProfile
    from app.models.intervention import Intervention
    from app.models.user import User


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Avis conditionné à une intervention terminée + contact vérifié (SMS).

    La digue anti-faux-avis de Checkatrade (90 % de leurs avis sont
    vérifiés) : un `review` ne peut exister que si l'`intervention` liée est
    `terminee`. Garantie en double :
    - couche service (`app.services.reviews.ensure_intervention_completed`),
      qui échoue vite avec un message clair avant toute écriture ;
    - trigger PostgreSQL `review_requires_completed_intervention` posé en
      migration (BEFORE INSERT/UPDATE OF intervention_id sur `review`),
      filet de sécurité pour toute écriture qui contournerait la couche
      service (script, admin SQL direct, futur import).

    Ne disparaît jamais en cascade : `intervention_id`/`author_id`/
    `artisan_id` sont en `ON DELETE RESTRICT`, pas `CASCADE`.

    Modération (BUILD_PLAN.md §3.6) : l'artisan concerné peut SIGNALER un
    avis une seule fois, avec un motif (`report_reason`/`reported_at`, posés
    ensemble et conservés comme historique). Un avis signalé reste visible et
    compté dans la note jusqu'à la décision d'un admin (masquer ou maintenir)
    : signaler ne suffit jamais à faire disparaître une critique. Un avis
    n'est jamais supprimé ; le masquage est réversible et journalisé.
    """

    __tablename__ = "review"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_between_1_and_5"),
        CheckConstraint(
            "(report_reason IS NULL) = (reported_at IS NULL)", name="report_fields_together"
        ),
        # Un avis « signalé » porte toujours le motif de son signalement.
        CheckConstraint(
            "status <> 'signale' OR reported_at IS NOT NULL", name="signale_has_report"
        ),
    )

    intervention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intervention.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artisan_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    contact_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.PUBLIE,
        index=True,
    )

    report_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    intervention: Mapped["Intervention"] = relationship(back_populates="review")
    author: Mapped["User"] = relationship(back_populates="reviews_written")
    artisan: Mapped["ArtisanProfile"] = relationship(back_populates="reviews_received")
