"""ajout decline_reason sur intervention

Revision ID: f35086f6d699
Revises: 285a1b35bc05
Create Date: 2026-07-25 14:16:20.014530

Motif optionnel du refus par l'artisan (BUILD_PLAN.md §6 Lot 12b,
`POST /interventions/{id}/decline`) : jamais exploité par une contrainte ou
un trigger, purement informatif (visible par le client, utile pour un futur
score de fiabilité artisan, BUILD_PLAN.md §8).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f35086f6d699"
down_revision: str | Sequence[str] | None = "285a1b35bc05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("intervention", sa.Column("decline_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("intervention", "decline_reason")
