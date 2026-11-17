"""notifications push : abonnements Web Push des appareils

Revision ID: 03131b25ffa4
Revises: a9fc7e20c661
Create Date: 2026-11-16 15:02:00.000000

Un abonnement par appareil (`endpoint` UNIQUE, fourni par le service de
push du navigateur), rattaché à son utilisateur et supprimé avec lui
(CASCADE). `p256dh`/`auth` : clés publiques du navigateur pour le
chiffrement de bout en bout (RFC 8291). CHECK : adresse https:// et
longueur bornée (défense en profondeur, le service filtre déjà l'hôte).

Nouvelle table seule : aucune donnée existante touchée. Réversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "03131b25ffa4"
down_revision: str | Sequence[str] | None = "a9fc7e20c661"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscription",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=128), nullable=False),
        sa.Column("auth", sa.String(length=64), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "endpoint LIKE 'https://%'", name=op.f("ck_push_subscription_endpoint_https")
        ),
        sa.CheckConstraint(
            "char_length(endpoint) <= 2048", name=op.f("ck_push_subscription_endpoint_max_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_push_subscription_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscription")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscription_endpoint")),
    )
    op.create_index(
        op.f("ix_push_subscription_user_id"), "push_subscription", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_push_subscription_user_id"), table_name="push_subscription")
    op.drop_table("push_subscription")
