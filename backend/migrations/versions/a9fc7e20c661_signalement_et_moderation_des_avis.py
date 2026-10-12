"""avis : signalement par l'artisan et modération admin

Revision ID: a9fc7e20c661
Revises: 40350384af35
Create Date: 2026-10-12 12:21:34.704628

Back-office (BUILD_PLAN.md §3.6) : l'artisan concerné peut signaler un avis
une fois, avec un motif (`report_reason`/`reported_at`, posés ensemble :
CHECK `report_fields_together`). Un avis au statut `signale` porte toujours
son signalement (CHECK `signale_has_report`).

Aucun point d'entrée ne posait `signale` avant cette migration ; par
prudence, une éventuelle ligne `signale` héritée reçoit un signalement daté
de sa création et un motif qui dit honnêtement qu'il n'a pas été enregistré,
plutôt que de faire échouer la contrainte. Réversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9fc7e20c661"
down_revision: str | Sequence[str] | None = "40350384af35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("review", sa.Column("report_reason", sa.Text(), nullable=True))
    op.add_column("review", sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE review SET reported_at = created_at, "
        "report_reason = 'Signalement antérieur : motif non enregistré.' "
        "WHERE status = 'signale'"
    )
    op.create_check_constraint(
        op.f("ck_review_report_fields_together"),
        "review",
        "(report_reason IS NULL) = (reported_at IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_review_signale_has_report"),
        "review",
        "status <> 'signale' OR reported_at IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_review_signale_has_report"), "review", type_="check")
    op.drop_constraint(op.f("ck_review_report_fields_together"), "review", type_="check")
    op.drop_column("review", "reported_at")
    op.drop_column("review", "report_reason")
