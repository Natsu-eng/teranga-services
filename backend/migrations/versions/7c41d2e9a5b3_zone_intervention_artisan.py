"""zone d'intervention : source de la position, quartier, grille et plafond du rayon

Revision ID: 7c41d2e9a5b3
Revises: 55f1da51e156
Create Date: 2026-11-21 10:00:00.000000

- `artisan_profile.location_source` (`neighborhood` | `gps`, NULL = non placé)
  et `artisan_profile.neighborhood_id` (identifiant de la liste fermée
  `app.core.neighborhoods`), avec une contrainte qui les garde cohérents avec
  `base_location`.
- Les positions déjà en base deviennent `gps` et sont ARRONDIES sur la grille
  ARTISAN_GPS_GRID_M, avec exactement le même calcul que l'application
  (`app.core.geo_privacy.snap_to_grid`, réglages lus comme au démarrage).
- Les rayons d'intervention au-delà de ARTISAN_SERVICE_RADIUS_MAX_M sont
  ramenés au plafond ; chaque correction est inscrite au journal d'audit
  (`artisan.location_change`, sans acteur, sans coordonnée).
- Journal d'audit : nouvelle action `artisan.location_change` (contrainte
  CHECK de l'énumération recréée). Elle fait 23 caractères : la colonne
  `audit_log.action` (VARCHAR à la longueur de la plus longue valeur, 22
  jusqu'ici) est élargie à 23, comme le modèle la déclare désormais.

Aucune coordonnée n'est écrite dans les journaux de migration : seulement
des nombres de lignes.

Downgrade : retire colonnes et contraintes. Il NE rend PAS les positions
précises ni les anciens rayons (ils ne sont conservés nulle part, c'est le
but). `audit_log` est en AJOUT SEUL : si des changements de zone y sont
journalisés (y compris les plafonnements faits par cet upgrade), l'ancienne
contrainte ne peut pas être remise et le downgrade s'arrête avec un message
explicite plutôt que de casser le journal.
"""

import json
import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings
from app.core.geo_privacy import snap_to_grid

# revision identifiers, used by Alembic.
revision: str = "7c41d2e9a5b3"
down_revision: str | Sequence[str] | None = "55f1da51e156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

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
    "support_ticket.reply",
)
_NEW_ACTION = "artisan.location_change"
LOCATION_FIELDS_CONSISTENT_SQL = (
    "(location_source IS NULL AND neighborhood_id IS NULL AND base_location IS NULL)"
    " OR (location_source IS NOT NULL AND base_location IS NOT NULL AND ("
    "(location_source = 'gps' AND neighborhood_id IS NULL)"
    " OR (location_source = 'neighborhood' AND neighborhood_id IS NOT NULL)))"
)
# Longueur de `audit_log.action` : celle de la plus longue valeur de
# l'énumération, avant (« commission_rate.create ») et après cette révision.
_ACTION_LENGTH_BEFORE = max(len(action) for action in _ACTIONS_BEFORE)
_ACTION_LENGTH_AFTER = max(_ACTION_LENGTH_BEFORE, len(_NEW_ACTION))
_SOURCES = ("neighborhood", "gps")


def _in_list(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _replace_audit_action_check(actions: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_audit_log_audit_log_action"), "audit_log", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_log_audit_log_action"), "audit_log", _in_list("action", actions)
    )


def _snap_existing_positions(bind: sa.engine.Connection) -> None:
    """Arrondit chaque position existante sur la grille, ligne par ligne (le
    calcul est celui de l'application, en Python, pour qu'une position
    arrondie ici soit identique à une position arrondie à l'écriture)."""
    settings = get_settings()
    rows = bind.execute(
        sa.text(
            "SELECT id, ST_Y(base_location::geometry) AS lat, ST_X(base_location::geometry) AS lng"
            " FROM artisan_profile WHERE base_location IS NOT NULL"
        )
    ).all()
    for row in rows:
        lat, lng = snap_to_grid(
            row.lat,
            row.lng,
            grid_m=settings.artisan_gps_grid_m,
            reference_lat=settings.service_region_center_lat,
        )
        bind.execute(
            sa.text(
                "UPDATE artisan_profile SET location_source = 'gps',"
                " base_location = ST_GeogFromText(:wkt) WHERE id = :id"
            ),
            {"wkt": f"SRID=4326;POINT({lng} {lat})", "id": row.id},
        )
    logger.info(
        "Zone d'intervention : %d position(s) arrondie(s) sur une grille de %d m.",
        len(rows),
        settings.artisan_gps_grid_m,
    )


def _cap_radii(bind: sa.engine.Connection) -> None:
    """Ramène au plafond les rayons qui le dépassent, et journalise chacun."""
    cap = get_settings().artisan_service_radius_max_m
    rows = bind.execute(
        sa.text(
            "SELECT at.id, at.artisan_id, at.service_radius_m, t.code AS trade_code"
            " FROM artisan_trade at JOIN trade t ON t.id = at.trade_id"
            " WHERE at.service_radius_m > :cap"
        ),
        {"cap": cap},
    ).all()
    for row in rows:
        bind.execute(
            sa.text("UPDATE artisan_trade SET service_radius_m = :cap WHERE id = :id"),
            {"cap": cap, "id": row.id},
        )
        details = {
            "kind": "radius",
            "reason": "plafond_migration",
            "counted": False,
            "first_placement": False,
            "trade_code": row.trade_code,
            "old_radius_m": row.service_radius_m,
            "new_radius_m": cap,
        }
        bind.execute(
            sa.text(
                "INSERT INTO audit_log (id, actor_id, actor_name, action, target_type,"
                " target_id, details)"
                " VALUES (:id, NULL, NULL, :action, 'artisan', :target, CAST(:details AS jsonb))"
            ),
            {
                "id": uuid.uuid4(),
                "action": _NEW_ACTION,
                "target": row.artisan_id,
                "details": json.dumps(details),
            },
        )
    logger.info(
        "Zone d'intervention : %d rayon(s) ramené(s) au plafond de %d m (journalisés).",
        len(rows),
        cap,
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("artisan_profile", sa.Column("location_source", sa.String(12), nullable=True))
    op.add_column("artisan_profile", sa.Column("neighborhood_id", sa.String(64), nullable=True))
    op.create_check_constraint(
        op.f("ck_artisan_profile_artisan_profile_location_source"),
        "artisan_profile",
        _in_list("location_source", _SOURCES),
    )
    op.alter_column(
        "audit_log",
        "action",
        type_=sa.String(_ACTION_LENGTH_AFTER),
        existing_type=sa.String(_ACTION_LENGTH_BEFORE),
        existing_nullable=False,
    )
    _replace_audit_action_check((*_ACTIONS_BEFORE, _NEW_ACTION))

    _snap_existing_positions(bind)
    _cap_radii(bind)

    # Jamais NULL (un CHECK à NULL serait accepté) : texte figé ici, identique
    # à `LOCATION_FIELDS_CONSISTENT_SQL` du modèle (vérifié par un test).
    op.create_check_constraint(
        op.f("ck_artisan_profile_location_fields_consistent"),
        "artisan_profile",
        LOCATION_FIELDS_CONSISTENT_SQL,
    )


def downgrade() -> None:
    journaled = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM audit_log WHERE action = :action"),
            {"action": _NEW_ACTION},
        )
        .scalar_one()
    )
    if journaled:
        raise RuntimeError(
            f"Downgrade impossible : {journaled} ligne(s) du journal d'audit (ajout seul) "
            "concernent des changements de zone ; elles ne peuvent être ni modifiées ni "
            "supprimées."
        )
    op.drop_constraint(
        op.f("ck_artisan_profile_location_fields_consistent"), "artisan_profile", type_="check"
    )
    op.drop_constraint(
        op.f("ck_artisan_profile_artisan_profile_location_source"),
        "artisan_profile",
        type_="check",
    )
    op.drop_column("artisan_profile", "neighborhood_id")
    op.drop_column("artisan_profile", "location_source")
    _replace_audit_action_check(_ACTIONS_BEFORE)
    op.alter_column(
        "audit_log",
        "action",
        type_=sa.String(_ACTION_LENGTH_BEFORE),
        existing_type=sa.String(_ACTION_LENGTH_AFTER),
        existing_nullable=False,
    )
