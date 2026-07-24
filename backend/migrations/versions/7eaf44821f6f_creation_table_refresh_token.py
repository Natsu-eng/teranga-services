"""creation table refresh_token

Revision ID: 7eaf44821f6f
Revises: 7d276730af75
Create Date: 2026-07-24 18:27:44.164712

Ajout non prévu dans le schéma initial du Lot 7 (BUILD_PLAN.md §2.2, §4.2) :
sans persistance du refresh token, un token volé reste valide jusqu'à
expiration (jusqu'à 30 jours) sans qu'on puisse déconnecter un appareil
précis ni couper un compte compromis. Permet la rotation et la révocation
(y compris de toute la famille de tokens d'un utilisateur, en cas de rejeu
d'un token déjà révoqué -- signal de vol).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7eaf44821f6f"
down_revision: str | Sequence[str] | None = "7d276730af75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "refresh_token",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("jti", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_refresh_token_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_token")),
        sa.UniqueConstraint("jti", name=op.f("uq_refresh_token_jti")),
    )
    op.create_index(op.f("ix_refresh_token_user_id"), "refresh_token", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_refresh_token_user_id"), table_name="refresh_token")
    op.drop_table("refresh_token")
