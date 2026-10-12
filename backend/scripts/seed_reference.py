"""Données de référence de PRODUCTION (DEPLOYMENT.md, mise en ligne) :
métiers et taux de commission global initial. Sûr en production.

Idempotent : relancer ne duplique rien et ne modifie aucune donnée
existante (un taux global déjà en place est conservé tel quel). La création
du taux initial est inscrite au journal d'audit (auteur : script), comme
tout ajout de taux fait depuis le back-office.

Usage (Railway : `railway run --service backend python scripts/seed_reference.py`) :

    uv run python scripts/seed_reference.py
    uv run python scripts/seed_reference.py --rate-bps 0   # lancement sans commission

À ne pas confondre avec `scripts/seed.py` (données de DÉMONSTRATION,
refusé en production).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Exécuté comme un script de fichier (pas `python -m`) : Python met le
# dossier scripts/ sur sys.path, pas backend/. Sans ceci, `import app` échoue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import async_session_maker  # noqa: E402
from app.models.enums import AuditAction, AuditTargetType  # noqa: E402
from app.services import audit as audit_service  # noqa: E402
from app.services.reference_data import (  # noqa: E402
    DEFAULT_COMMISSION_RATE_BPS,
    ensure_default_commission_rate,
    ensure_trades,
)


async def seed_reference(session: AsyncSession, *, rate_bps: int) -> list[str]:
    """Applique les données de référence ; renvoie ce qui a été créé."""
    created: list[str] = []
    for code, (_, was_created) in (await ensure_trades(session)).items():
        if was_created:
            created.append(f"métier {code}")

    rate, was_created = await ensure_default_commission_rate(session, rate_bps=rate_bps)
    if was_created:
        await audit_service.record(
            session,
            actor=None,
            action=AuditAction.COMMISSION_RATE_CREATE,
            target_type=AuditTargetType.COMMISSION_RATE,
            target_id=rate.id,
            details={
                "rate_bps": rate.rate_bps,
                "trade_code": None,
                "effective_from": rate.effective_from,
                "via": "scripts/seed_reference.py",
            },
        )
        created.append(f"taux de commission global ({rate.rate_bps} points de base)")
    return created


def _rate(value: str) -> int:
    rate = int(value)
    if not 0 <= rate <= 10_000:
        raise argparse.ArgumentTypeError("entre 0 et 10000 points de base (10000 = 100 %)")
    return rate


async def main(rate_bps: int) -> None:
    async with async_session_maker() as session, session.begin():
        created = await seed_reference(session, rate_bps=rate_bps)
    if created:
        print("Créé : " + ", ".join(created) + ".")
    else:
        print("Rien à créer : les données de référence sont déjà en place.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rate-bps",
        type=_rate,
        default=DEFAULT_COMMISSION_RATE_BPS,
        help=(
            "taux global initial si aucun n'existe, en points de base "
            f"(défaut {DEFAULT_COMMISSION_RATE_BPS} = 10 %%)"
        ),
    )
    asyncio.run(main(parser.parse_args().rate_bps))
