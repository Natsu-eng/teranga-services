"""aide : demandes au support (support_ticket) et leur journal d'audit

Revision ID: 55f1da51e156
Revises: 03131b25ffa4
Create Date: 2026-11-20 15:59:07.991454

- Table `support_ticket` : une demande d'aide d'un client ou d'un artisan
  (catégorie, message masqué, intervention facultative), traitée par un
  admin (réponse, résolution). CHECK : réponse renseignée d'un bloc,
  `resolved_at` seulement au statut `resolu`.
- Journal d'audit : nouvelle action `support_ticket.reply` et nouvelle cible
  `support_ticket` -- les contraintes CHECK des deux énumérations sont
  recréées avec les valeurs ajoutées (rien d'autre ne change).

Downgrade : `audit_log` est en AJOUT SEUL (déclencheur) ; si des réponses à
des demandes d'aide y sont déjà journalisées, leurs lignes ne peuvent ni être
modifiées ni supprimées, donc l'ancienne contrainte ne peut pas être remise :
le downgrade s'arrête alors avec un message explicite plutôt que de casser le
journal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55f1da51e156"
down_revision: str | Sequence[str] | None = "03131b25ffa4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS_BEFORE = (
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
)
_TARGETS_BEFORE = ("verification", "intervention", "artisan", "user", "review", "commission_rate")
_NEW_ACTION = "support_ticket.reply"
_NEW_TARGET = "support_ticket"


def _in_list(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _replace_audit_checks(actions: Sequence[str], targets: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_audit_log_audit_log_action"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_audit_log_action"), "audit_log", _in_list("action", actions)
    )
    op.drop_constraint(op.f("ck_audit_log_audit_log_target_type"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_audit_log_target_type"), "audit_log", _in_list("target_type", targets)
    )


def upgrade() -> None:
    op.create_table(
        "support_ticket",
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column(
            "author_role",
            sa.Enum(
                "client",
                "artisan",
                "admin",
                name="support_ticket_author_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "compte",
                "utilisateur",
                "paiement",
                "bug",
                "autre",
                name="support_ticket_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("intervention_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ouvert",
                "resolu",
                name="support_ticket_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("admin_reply", sa.Text(), nullable=True),
        sa.Column("replied_by_id", sa.UUID(), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'resolu') = (resolved_at IS NOT NULL)",
            name=op.f("ck_support_ticket_resolved_at_matches_status"),
        ),
        sa.CheckConstraint(
            "(admin_reply IS NULL) = (replied_at IS NULL)"
            " AND (admin_reply IS NULL) = (replied_by_id IS NULL)",
            name=op.f("ck_support_ticket_reply_fields_together"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["user.id"],
            name=op.f("fk_support_ticket_author_id_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["intervention.id"],
            name=op.f("fk_support_ticket_intervention_id_intervention"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replied_by_id"],
            ["user.id"],
            name=op.f("fk_support_ticket_replied_by_id_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_ticket")),
    )
    op.create_index(
        "ix_support_ticket_author_created", "support_ticket", ["author_id", "created_at"]
    )
    op.create_index(
        op.f("ix_support_ticket_intervention_id"), "support_ticket", ["intervention_id"]
    )
    op.create_index("ix_support_ticket_status_created", "support_ticket", ["status", "created_at"])
    _replace_audit_checks((*_ACTIONS_BEFORE, _NEW_ACTION), (*_TARGETS_BEFORE, _NEW_TARGET))


def downgrade() -> None:
    journaled = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM audit_log WHERE action = :action OR target_type = :target"
            ),
            {"action": _NEW_ACTION, "target": _NEW_TARGET},
        )
        .scalar_one()
    )
    if journaled:
        raise RuntimeError(
            f"Downgrade impossible : {journaled} ligne(s) du journal d'audit (ajout seul) "
            "concernent des demandes d'aide ; elles ne peuvent être ni modifiées ni supprimées."
        )
    _replace_audit_checks(_ACTIONS_BEFORE, _TARGETS_BEFORE)
    op.drop_index("ix_support_ticket_status_created", table_name="support_ticket")
    op.drop_index(op.f("ix_support_ticket_intervention_id"), table_name="support_ticket")
    op.drop_index("ix_support_ticket_author_created", table_name="support_ticket")
    op.drop_table("support_ticket")
