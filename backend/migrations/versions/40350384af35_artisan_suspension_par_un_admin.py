"""artisan : suspension par un admin

Revision ID: 40350384af35
Revises: 3904df1e90b9
Create Date: 2026-10-12 12:08:25.842161

Back-office (BUILD_PLAN.md §3.6) : suspension d'un artisan par un admin,
distincte de la vérification. `suspended_at` NULL = actif ; motif
obligatoire (CHECK `suspension_fields_together`). Colonnes nullables : les
artisans existants restent actifs. Réversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "40350384af35"
down_revision: str | Sequence[str] | None = "3904df1e90b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "artisan_profile", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("artisan_profile", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_artisan_profile_suspension_fields_together"),
        "artisan_profile",
        "(suspended_at IS NULL) = (suspension_reason IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("ck_artisan_profile_suspension_fields_together"), "artisan_profile", type_="check"
    )
    op.drop_column("artisan_profile", "suspension_reason")
    op.drop_column("artisan_profile", "suspended_at")
