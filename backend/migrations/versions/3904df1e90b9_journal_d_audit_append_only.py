"""journal d'audit append-only

Revision ID: 3904df1e90b9
Revises: 1fcb7f06d5fe
Create Date: 2026-10-12 11:44:33.465734

Back-office admin (BUILD_PLAN.md §3.6) : `audit_log` journalise chaque
action admin sensible (acteur, action, cible, horodatage, détails).

**Ajout seul garanti par la base** : le déclencheur
`audit_log_append_only` refuse tout UPDATE et DELETE (par ligne) et tout
TRUNCATE (par instruction) -- ni l'API, ni un script, ni une requête SQL
directe ne peuvent réécrire ou effacer l'historique. Le downgrade retire
déclencheur, fonction et table (réversible).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3904df1e90b9"
down_revision: str | Sequence[str] | None = "1fcb7f06d5fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_log",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_name", sa.String(length=150), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "admin.bootstrap",
                "verification.approve",
                "verification.reject",
                "dispute.resolve",
                "artisan.suspend",
                "artisan.reactivate",
                "user.grant_admin",
                "user.revoke_admin",
                "review.hide",
                "review.restore",
                "commission_rate.create",
                name="audit_log_action",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.Enum(
                "verification",
                "intervention",
                "artisan",
                "user",
                "review",
                "commission_rate",
                name="audit_log_target_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["user.id"], name=op.f("fk_audit_log_actor_id_user"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index("ix_audit_log_target", "audit_log", ["target_type", "target_id"], unique=False)
    op.execute(
        """
        CREATE FUNCTION audit_log_refuse_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log est en ajout seul : modification et suppression interdites'
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_refuse_change()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_refuse_change()")
    op.drop_index("ix_audit_log_target", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
