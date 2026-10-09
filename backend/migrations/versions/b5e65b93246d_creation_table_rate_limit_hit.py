"""creation table rate_limit_hit

Revision ID: b5e65b93246d
Revises: f35086f6d699
Create Date: 2026-10-09 22:39:10.928921

Rate limiting partagé (lot `feat/media-hardening`) : remplace l'état en
mémoire par processus, qui ne survivait ni à un redémarrage ni à plusieurs
instances (limite réelle multipliée par le nombre de workers). Une ligne
par appel décompté ; la clé (numéro, IP, utilisateur) n'est jamais stockée
en clair, seulement son empreinte SHA-256 -- voir
`app.services.rate_limit.PostgresRateLimiter`. Table purement technique,
sans clé étrangère : la purger (même entièrement) ne fait que remettre les
compteurs à zéro.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e65b93246d"
down_revision: str | Sequence[str] | None = "f35086f6d699"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rate_limit_hit",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bucket", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "hit_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_hit")),
    )
    op.create_index(
        "ix_rate_limit_hit_bucket_key_hash_hit_at",
        "rate_limit_hit",
        ["bucket", "key_hash", "hit_at"],
        unique=False,
    )
    op.create_index("ix_rate_limit_hit_hit_at", "rate_limit_hit", ["hit_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_rate_limit_hit_hit_at", table_name="rate_limit_hit")
    op.drop_index("ix_rate_limit_hit_bucket_key_hash_hit_at", table_name="rate_limit_hit")
    op.drop_table("rate_limit_hit")
