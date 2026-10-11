"""demande : libelle du lieu confirme par le client

Revision ID: 1fcb7f06d5fe
Revises: b25862fcd340
Create Date: 2026-10-12 10:00:00.000000

Localisation explicite de la demande (lot `fix/localisation-demande`) : le
client choisit et VOIT le lieu de son intervention (quartier ou « Ma
position actuelle ») avant d'envoyer. `service_request.location_label`
conserve ce libellé à côté des coordonnées. Colonne nullable : les demandes
antérieures (localisées par le GPS du navigateur, sans libellé) restent
valides telles quelles.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1fcb7f06d5fe"
down_revision: str | Sequence[str] | None = "b25862fcd340"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "service_request", sa.Column("location_label", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("service_request", "location_label")
