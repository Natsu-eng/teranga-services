"""ajout rating_avg et review_count sur artisan_profile

Revision ID: 285a1b35bc05
Revises: 7eaf44821f6f
Create Date: 2026-07-24 21:50:39.135096

Dénormalisation en lecture (BUILD_PLAN.md §6, Lot 9) : `AVG(rating)` par
artisan sur chaque requête de liste ne tient pas à l'échelle. Les deux
colonnes sont recalculées par `app.services.reviews.recalculate_artisan_rating`
après toute mutation d'un avis publié, jamais écrites à la main.

`server_default="0"` sur `review_count` est transitoire : requis pour que les
lignes déjà en base (artisans semés par un run précédent de `scripts/seed.py`)
passent la contrainte NOT NULL au moment de l'upgrade, puis retiré
immédiatement pour ne pas diverger du défaut Python de l'ORM
(`mapped_column(default=0)`, pas un défaut serveur).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "285a1b35bc05"
down_revision: str | Sequence[str] | None = "7eaf44821f6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "artisan_profile", sa.Column("rating_avg", sa.Numeric(precision=3, scale=2), nullable=True)
    )
    op.add_column(
        "artisan_profile",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("artisan_profile", "review_count", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("artisan_profile", "review_count")
    op.drop_column("artisan_profile", "rating_avg")
