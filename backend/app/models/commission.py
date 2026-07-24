import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SubscriptionTier
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.payment import PlatformFee
    from app.models.trade import Trade


class CommissionRate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Taux de commission versionné, avec dates d'effet.

    Le taux n'est **jamais en dur** : le taux appliqué à une intervention
    passée reste figé sur `intervention.commission_rate_id` (comptabilité,
    litiges, confiance). `trade_id`/`tier` nuls = s'applique à tous.

    Non-chevauchement : une contrainte d'exclusion PostgreSQL (EXCLUDE USING
    gist, nécessite l'extension `btree_gist`) interdit deux lignes en
    vigueur simultanément pour le même couple (trade_id, tier), y compris
    entre lignes déjà closes (`effective_to` renseigné) — une simple
    contrainte d'unicité partielle sur `effective_to IS NULL` ne protégerait
    que la ligne "courante" et laisserait passer un chevauchement entre deux
    lignes historiques mal saisies. `trade_id`/`tier` NULL (portée "tous")
    sont neutralisés via `coalesce(...)` vers une sentinelle non nulle : en
    SQL, `NULL = NULL` est indéterminé et laisserait sinon passer plusieurs
    lignes "tous métiers"/"tous paliers" qui se chevauchent.
    """

    __tablename__ = "commission_rate"
    __table_args__ = (
        CheckConstraint("rate_bps >= 0 AND rate_bps <= 10000", name="rate_bps_between_0_and_10000"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="effective_to_after_effective_from",
        ),
        ExcludeConstraint(
            (text("coalesce(trade_id, '00000000-0000-0000-0000-000000000000'::uuid)"), "="),
            (text("coalesce(tier::text, '__all__')"), "="),
            (
                text("tstzrange(effective_from, coalesce(effective_to, 'infinity'::timestamptz))"),
                "&&",
            ),
            name="commission_rate_no_time_overlap",
        ),
    )

    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade.id", ondelete="RESTRICT"), index=True
    )
    tier: Mapped[SubscriptionTier | None] = mapped_column(
        enum_column(SubscriptionTier, "commission_rate_tier")
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trade: Mapped["Trade | None"] = relationship()
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="commission_rate")
    platform_fees: Mapped[list["PlatformFee"]] = relationship(back_populates="commission_rate")
