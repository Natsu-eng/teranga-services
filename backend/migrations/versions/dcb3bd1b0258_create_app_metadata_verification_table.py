"""création de la table technique de vérification app_metadata

Revision ID: dcb3bd1b0258
Revises:
Create Date: 2026-07-23 13:57:41.689568

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dcb3bd1b0258"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Table technique minimale pour vérifier que le pipeline de migration
    atteint bien Postgres de bout en bout (Lot 6). Pas de modèle métier
    pour l'instant — ça commence au Lot 7.
    """
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("app_metadata")
