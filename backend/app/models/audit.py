import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AuditAction, AuditTargetType
from app.models.mixins import UUIDPrimaryKeyMixin, enum_column


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Journal d'audit des actions admin sensibles (BUILD_PLAN.md §3.6).

    **Ajout seul, garanti par la base** : un déclencheur PostgreSQL
    (`audit_log_append_only`, migration) refuse tout UPDATE, DELETE ou
    TRUNCATE -- même une requête SQL directe ou un futur code fautif ne peut
    réécrire l'histoire. Aucune route ne modifie ni ne supprime une ligne.

    Chaque ligne est écrite dans la MÊME transaction que l'action qu'elle
    décrit : une action validée est toujours journalisée, une action
    annulée ne l'est jamais.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_target", "target_type", "target_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    # Horloge réelle (pas l'heure de début de transaction) : plusieurs
    # actions d'une même transaction restent ordonnées.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    # NULL : action hors application (script CLI de bootstrap).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), index=True
    )
    # Nom de l'acteur AU MOMENT de l'action (un nom peut changer ensuite).
    actor_name: Mapped[str | None] = mapped_column(String(150))
    action: Mapped[AuditAction] = mapped_column(
        enum_column(AuditAction, "audit_log_action"), nullable=False, index=True
    )
    target_type: Mapped[AuditTargetType] = mapped_column(
        enum_column(AuditTargetType, "audit_log_target_type"), nullable=False
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Contexte de la décision (motif, ancienne/nouvelle valeur...). Jamais de
    # secret ni de numéro de téléphone.
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
