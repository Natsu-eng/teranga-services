"""Mixins déclaratifs partagés par tous les modèles ORM."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def enum_column(enum_cls: type[PyEnum], name: str, **kwargs: Any) -> SAEnum:
    """Construit une colonne enum non native (VARCHAR + CHECK côté base).

    `native_enum=False` : un type PostgreSQL natif (CREATE TYPE ... AS ENUM)
    ne s'altère pas proprement (ajouter/retirer une valeur est une opération
    DDL délicate) et Alembic ne le supprime pas au downgrade, ce qui casserait
    la réversibilité des migrations (cf. BUILD_PLAN.md §2.2).

    `values_callable` : sans lui, SQLAlchemy persiste le *nom* Python de
    l'enum (ex. "TERMINEE"), pas sa *valeur* (ex. "terminee") -- or c'est la
    valeur qui est le vocabulaire métier documenté dans BUILD_PLAN.md et
    attendu par le SQL écrit à la main (triggers, requêtes ad hoc).

    `create_constraint=True` : depuis SQLAlchemy 2.0, un `Enum` non natif ne
    pose PAS de CHECK par défaut (choix conservateur de la librairie). Sans
    ce paramètre explicite, la colonne ne serait qu'un VARCHAR non contraint
    -- silencieusement, aucune valeur invalide ne serait jamais rejetée.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
        values_callable=lambda cls: [member.value for member in cls],
        **kwargs,
    )


class UUIDPrimaryKeyMixin:
    """Clé primaire UUID générée côté application (pas de séquence)."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """`created_at` en timestamptz, posé côté base. Pour les tables en lecture
    seule après création (verification, quote, commission_rate, payment
    intermédiaires, review, message, otp_code…) où l'horodatage de la
    transition d'état, s'il existe, a déjà sa propre colonne dédiée
    (`reviewed_at`, `paid_at`, `sent_at`…)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """`created_at`/`updated_at` en timestamptz, pour les entités dont le
    statut évolue après création sans colonne de transition dédiée."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """Suppression logique : `deleted_at` non nul marque une ligne supprimée."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
