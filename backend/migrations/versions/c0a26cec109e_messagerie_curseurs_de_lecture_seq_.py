"""messagerie : curseurs de lecture, seq, masquage, pieces jointes

Revision ID: c0a26cec109e
Revises: b5e65b93246d
Create Date: 2026-10-11 15:33:55.636767

Messagerie in-app client ↔ artisan (BUILD_PLAN.md §3.2, Messagerie). Les
tables `conversation`/`message` existent depuis le schéma initial (Lot 7)
mais n'étaient exposées par aucun endpoint. Cette migration ajoute :

- `conversation.client_last_read_seq` / `artisan_last_read_seq` : curseur de
  lecture de chaque participant (compteur de non-lus) ;
- `conversation.last_message_at` : tri de la liste par activité récente ;
- unicité partielle de `conversation.intervention_id` : au plus une
  conversation par intervention ;
- `message.seq` : numéro d'ordre strictement croissant (identité Postgres),
  curseur de l'historique et du repli polling (`?since=`) ;
- `message.contact_masked` : trace d'une tentative de partage de numéro,
  sans jamais conserver le numéro lui-même ;
- `message.attachment_key` / `attachment_content_type` : image jointe,
  stockée en privé ;
- deux CHECK : un message porte du texte ou une image ; référence et type de
  la pièce jointe vont ensemble.

Rattrapage des données : une conversation est créée pour chaque
intervention existante qui n'en a pas (idempotent, respecte l'index
unique) -- l'invariant « toute intervention a son fil » vaut aussi pour les
interventions antérieures à cette migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0a26cec109e"
down_revision: str | Sequence[str] | None = "b5e65b93246d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "conversation",
        sa.Column("client_last_read_seq", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversation",
        sa.Column("artisan_last_read_seq", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversation", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_conversation_client_last_read_seq_gte_0"),
        "conversation",
        "client_last_read_seq >= 0",
    )
    op.create_check_constraint(
        op.f("ck_conversation_artisan_last_read_seq_gte_0"),
        "conversation",
        "artisan_last_read_seq >= 0",
    )
    op.create_index(
        "uq_conversation_intervention_id",
        "conversation",
        ["intervention_id"],
        unique=True,
        postgresql_where=sa.text("intervention_id IS NOT NULL"),
    )

    op.add_column(
        "message",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
    )
    op.add_column(
        "message",
        sa.Column("contact_masked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("message", sa.Column("attachment_key", sa.Text(), nullable=True))
    op.add_column(
        "message", sa.Column("attachment_content_type", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_message_seq"), "message", ["seq"])
    op.create_index(
        "ix_message_conversation_id_seq", "message", ["conversation_id", "seq"], unique=False
    )
    op.create_check_constraint(
        op.f("ck_message_body_or_attachment"),
        "message",
        "char_length(body) > 0 OR attachment_key IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_message_attachment_complete"),
        "message",
        "(attachment_key IS NULL) = (attachment_content_type IS NULL)",
    )

    # Rattrapage : un fil pour chaque intervention existante qui n'en a pas.
    # `conversation.artisan_id` référence le COMPTE de l'artisan (user.id),
    # résolu via artisan_profile.user_id.
    op.execute(
        """
        INSERT INTO conversation (id, service_request_id, intervention_id, client_id, artisan_id)
        SELECT gen_random_uuid(), i.service_request_id, i.id, i.client_id, ap.user_id
        FROM intervention i
        JOIN artisan_profile ap ON ap.id = i.artisan_id
        WHERE NOT EXISTS (
            SELECT 1 FROM conversation c WHERE c.intervention_id = i.id
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema.

    Les conversations créées par le rattrapage sont conservées (elles étaient
    valides au regard du schéma initial) ; seules les colonnes et contraintes
    ajoutées sont retirées.
    """
    op.drop_constraint(op.f("ck_message_attachment_complete"), "message", type_="check")
    op.drop_constraint(op.f("ck_message_body_or_attachment"), "message", type_="check")
    op.drop_index("ix_message_conversation_id_seq", table_name="message")
    op.drop_constraint(op.f("uq_message_seq"), "message", type_="unique")
    op.drop_column("message", "attachment_content_type")
    op.drop_column("message", "attachment_key")
    op.drop_column("message", "contact_masked")
    op.drop_column("message", "seq")
    op.drop_index(
        "uq_conversation_intervention_id",
        table_name="conversation",
        postgresql_where=sa.text("intervention_id IS NOT NULL"),
    )
    op.drop_constraint(
        op.f("ck_conversation_artisan_last_read_seq_gte_0"), "conversation", type_="check"
    )
    op.drop_constraint(
        op.f("ck_conversation_client_last_read_seq_gte_0"), "conversation", type_="check"
    )
    op.drop_column("conversation", "last_message_at")
    op.drop_column("conversation", "artisan_last_read_seq")
    op.drop_column("conversation", "client_last_read_seq")
