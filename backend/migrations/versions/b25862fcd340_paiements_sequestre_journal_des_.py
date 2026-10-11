"""paiements : sequestre, journal des webhooks, annulation et litige

Revision ID: b25862fcd340
Revises: c0a26cec109e
Create Date: 2026-10-11 21:25:25.911835

Moteur de paiement (BUILD_PLAN.md §3.5). Les tables `payment`,
`platform_fee` et `payout` existent depuis le schéma initial (Lot 7) mais
n'étaient alimentées par aucun endpoint. Cette migration :

- `payment` : nouveaux statuts du séquestre (`retenu`, `libere`, `annule`),
  fournisseur et référence (unique par fournisseur), page de paiement et
  son expiration, horodatages de libération/remboursement ; au plus UN
  paiement vivant par intervention (index unique partiel) ; le cash n'a
  jamais de fournisseur, un paiement en ligne toujours un (CHECK) ;
- `payment_event` : journal des webhooks, `(provider, event_id)` unique --
  la clé d'idempotence. Remplace `payment.wave_event_id`, propre à un seul
  fournisseur et incapable de tracer plusieurs événements par paiement ;
- `platform_fee` : une seule commission par intervention, `settled_at` ;
- `payout` : un seul versement par intervention, numéro de destination
  (copie du numéro vérifié du compte, pour l'audit), fournisseur,
  tentatives et motif d'échec ;
- `artisan_profile.payout_channel` : moyen de versement choisi ;
- `intervention` : clôture par annulation (`cancelled_at`, `cancelled_by`,
  `cancellation_kind`, `cancellation_reason`), qui remplace
  `decline_reason` (les motifs existants sont repris tels quels, en
  « refus » par l'artisan) ;
- `intervention_dispute` : litige qui gèle le séquestre jusqu'à décision
  d'un admin.

Downgrade : avec perte assumée sur les seules données nées de ce lot --
les statuts `retenu`/`libere` redeviennent `reussi`, `annule` redevient
`echoue` (l'ancien schéma ne sait pas les représenter).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b25862fcd340"
down_revision: str | Sequence[str] | None = "c0a26cec109e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_PAYMENT_STATUSES = ("en_attente", "reussi", "echoue", "rembourse")
_NEW_PAYMENT_STATUSES = (
    "en_attente",
    "retenu",
    "libere",
    "reussi",
    "echoue",
    "annule",
    "rembourse",
)
_ACTIVE_PAYMENT_STATUSES = "status IN ('en_attente', 'retenu', 'libere', 'reussi')"


def _status_check(values: Sequence[str]) -> str:
    return "status IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    """Upgrade schema."""
    # --- payment : statuts du séquestre ---------------------------------------
    op.drop_constraint(op.f("ck_payment_payment_status"), "payment", type_="check")
    op.create_check_constraint(
        op.f("ck_payment_payment_status"), "payment", _status_check(_NEW_PAYMENT_STATUSES)
    )

    op.add_column("payment", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("payment", sa.Column("checkout_url", sa.Text(), nullable=True))
    op.add_column(
        "payment", sa.Column("checkout_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("payment", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payment", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payment", sa.Column("refund_ref", sa.String(length=255), nullable=True))
    # Paiements antérieurs en ligne (jeux de test) : fournisseur historique.
    op.execute("UPDATE payment SET provider = 'legacy' WHERE channel <> 'cash'")
    op.create_check_constraint(
        op.f("ck_payment_provider_iff_online_channel"),
        "payment",
        "(channel = 'cash') = (provider IS NULL)",
    )
    op.drop_constraint(op.f("uq_payment_wave_event_id"), "payment", type_="unique")
    op.drop_column("payment", "wave_event_id")
    op.create_unique_constraint(
        "uq_payment_provider_provider_ref", "payment", ["provider", "provider_ref"]
    )
    op.create_index(
        "uq_payment_active_intervention_id",
        "payment",
        ["intervention_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_PAYMENT_STATUSES),
    )

    # --- payment_event : journal idempotent des webhooks --------------------------
    op.create_table(
        "payment_event",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payment.id"],
            name=op.f("fk_payment_event_payment_id_payment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_event")),
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_event_provider_event_id"),
    )
    op.create_index(
        op.f("ix_payment_event_payment_id"), "payment_event", ["payment_id"], unique=False
    )

    # --- platform_fee : une commission par intervention -------------------------
    op.add_column(
        "platform_fee", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "uq_platform_fee_commission_intervention_id",
        "platform_fee",
        ["intervention_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'commission'"),
    )

    # --- payout : un versement par intervention, traçable -------------------------
    # server_default temporaires : remplissent d'éventuelles lignes existantes,
    # puis retirés -- le code renseigne toujours ces colonnes explicitement.
    op.add_column(
        "payout",
        sa.Column("destination_phone", sa.String(length=20), server_default="", nullable=False),
    )
    op.add_column(
        "payout",
        sa.Column("provider", sa.String(length=32), server_default="legacy", nullable=False),
    )
    op.add_column("payout", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.alter_column("payout", "destination_phone", server_default=None)
    op.alter_column("payout", "provider", server_default=None)
    op.alter_column("payout", "attempts", server_default=None)
    op.add_column("payout", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payout", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.create_check_constraint(op.f("ck_payout_attempts_gte_0"), "payout", "attempts >= 0")
    op.drop_index(op.f("ix_payout_intervention_id"), table_name="payout")
    op.create_unique_constraint("uq_payout_intervention_id", "payout", ["intervention_id"])

    # --- artisan_profile : moyen de versement -------------------------------------
    op.add_column(
        "artisan_profile",
        sa.Column(
            "payout_channel",
            _enum("artisan_profile_payout_channel", "wave", "orange_money", "bank"),
            nullable=True,
        ),
    )

    # --- intervention : clôture par annulation -------------------------------------
    op.add_column(
        "intervention", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "intervention",
        sa.Column(
            "cancelled_by",
            _enum("intervention_cancelled_by", "client", "artisan", "admin"),
            nullable=True,
        ),
    )
    op.add_column(
        "intervention",
        sa.Column(
            "cancellation_kind",
            _enum("intervention_cancellation_kind", "refus", "annulation", "arbitrage"),
            nullable=True,
        ),
    )
    op.add_column("intervention", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    # Seul chemin d'annulation jusqu'ici : le refus par l'artisan.
    op.execute(
        "UPDATE intervention SET cancelled_at = updated_at, cancelled_by = 'artisan',"
        " cancellation_kind = 'refus', cancellation_reason = decline_reason"
        " WHERE status = 'annulee'"
    )
    op.drop_column("intervention", "decline_reason")
    op.create_check_constraint(
        op.f("ck_intervention_cancellation_fields_together"),
        "intervention",
        "(cancelled_at IS NULL) = (cancellation_kind IS NULL)"
        " AND (cancelled_at IS NULL) = (cancelled_by IS NULL)",
    )

    # --- intervention_dispute : litige -------------------------------------------
    op.create_table(
        "intervention_dispute",
        sa.Column("intervention_id", sa.UUID(), nullable=False),
        sa.Column("opened_by_id", sa.UUID(), nullable=False),
        sa.Column(
            "opened_by_role",
            _enum("intervention_dispute_opened_by_role", "client", "artisan", "admin"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "outcome",
            _enum("intervention_dispute_outcome", "libere", "rembourse"),
            nullable=True,
        ),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (resolved_at IS NULL)"
            " AND (outcome IS NULL) = (resolved_by_id IS NULL)",
            name=op.f("ck_intervention_dispute_resolution_fields_together"),
        ),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["intervention.id"],
            name=op.f("fk_intervention_dispute_intervention_id_intervention"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_id"],
            ["user.id"],
            name=op.f("fk_intervention_dispute_opened_by_id_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["user.id"],
            name=op.f("fk_intervention_dispute_resolved_by_id_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intervention_dispute")),
        sa.UniqueConstraint(
            "intervention_id", name=op.f("uq_intervention_dispute_intervention_id")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("intervention_dispute")

    op.drop_constraint(
        op.f("ck_intervention_cancellation_fields_together"), "intervention", type_="check"
    )
    op.add_column("intervention", sa.Column("decline_reason", sa.Text(), nullable=True))
    op.execute(
        "UPDATE intervention SET decline_reason = cancellation_reason"
        " WHERE cancellation_kind = 'refus'"
    )
    op.drop_column("intervention", "cancellation_reason")
    op.drop_column("intervention", "cancellation_kind")
    op.drop_column("intervention", "cancelled_by")
    op.drop_column("intervention", "cancelled_at")

    op.drop_column("artisan_profile", "payout_channel")

    op.drop_constraint("uq_payout_intervention_id", "payout", type_="unique")
    op.create_index(op.f("ix_payout_intervention_id"), "payout", ["intervention_id"], unique=False)
    op.drop_constraint(op.f("ck_payout_attempts_gte_0"), "payout", type_="check")
    op.drop_column("payout", "failure_reason")
    op.drop_column("payout", "last_attempt_at")
    op.drop_column("payout", "attempts")
    op.drop_column("payout", "provider")
    op.drop_column("payout", "destination_phone")

    op.drop_index("uq_platform_fee_commission_intervention_id", table_name="platform_fee")
    op.drop_column("platform_fee", "settled_at")

    op.drop_index(op.f("ix_payment_event_payment_id"), table_name="payment_event")
    op.drop_table("payment_event")

    op.drop_index("uq_payment_active_intervention_id", table_name="payment")
    op.drop_constraint("uq_payment_provider_provider_ref", "payment", type_="unique")
    op.add_column("payment", sa.Column("wave_event_id", sa.String(length=255), nullable=True))
    op.create_unique_constraint(op.f("uq_payment_wave_event_id"), "payment", ["wave_event_id"])
    op.drop_constraint(op.f("ck_payment_provider_iff_online_channel"), "payment", type_="check")
    op.drop_column("payment", "refund_ref")
    op.drop_column("payment", "refunded_at")
    op.drop_column("payment", "released_at")
    op.drop_column("payment", "checkout_expires_at")
    op.drop_column("payment", "checkout_url")
    op.drop_column("payment", "provider")
    op.drop_constraint(op.f("ck_payment_payment_status"), "payment", type_="check")
    op.execute(
        "UPDATE payment SET status = CASE status"
        " WHEN 'retenu' THEN 'reussi' WHEN 'libere' THEN 'reussi' WHEN 'annule' THEN 'echoue'"
        " ELSE status END"
    )
    op.create_check_constraint(
        op.f("ck_payment_payment_status"), "payment", _status_check(_OLD_PAYMENT_STATUSES)
    )
