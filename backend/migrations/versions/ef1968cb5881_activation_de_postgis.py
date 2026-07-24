"""activation de PostGIS

Revision ID: ef1968cb5881
Revises: dcb3bd1b0258
Create Date: 2026-07-24 14:39:29.430080

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ef1968cb5881"
down_revision: str | Sequence[str] | None = "dcb3bd1b0258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Active PostGIS : préalable à toute colonne `geography(...)` (Lot 7).
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS postgis")
