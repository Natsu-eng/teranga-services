"""Relance des versements aux artisans (BUILD_PLAN.md §3.5).

Un versement est envoyé juste après la complétion d'une intervention ; si
le fournisseur était indisponible, il reste `echoue` (ou `en_attente` si le
processus s'est arrêté entre le commit et l'envoi). Ce script les relance,
du plus ancien au plus récent.

Sans risque de double versement : chaque envoi porte la clé d'idempotence
`payout-<id>`, que le fournisseur reconnaît s'il l'a déjà traitée, et un
versement `envoye` n'est jamais relancé. À planifier (cron) ou à lancer à
la main par l'opérateur.

Usage :
    uv run python scripts/dispatch_payouts.py
    uv run python scripts/dispatch_payouts.py --limit 50
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Exécuté comme un script de fichier (pas `python -m`) : Python met le
# dossier scripts/ sur sys.path, pas backend/. Sans ceci, `import app` échoue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from app.models.enums import PayoutStatus  # noqa: E402
from app.services import payouts as payouts_service  # noqa: E402
from app.services.payment_providers import build_payment_provider  # noqa: E402

# Nombre de versements traités par exécution : borne la durée d'un passage
# (chaque envoi est un appel au fournisseur) ; le reste passera au suivant.
DEFAULT_LIMIT = 100


async def _run(limit: int) -> int:
    settings = get_settings()
    provider = build_payment_provider(settings)
    if provider is None:
        print("Paiement en ligne désactivé (PAYMENT_PROVIDER=disabled) : rien à verser.")
        return 0
    results = await payouts_service.dispatch_pending_payouts(
        async_session_maker, provider=provider, settings=settings, limit=limit
    )
    if not results:
        print("Aucun versement en attente.")
        return 0
    for status, count in results.items():
        label = status.value if status is not None else "erreur inattendue (voir les journaux)"
        print(f"{count} versement(s) : {label}")
    # Code de sortie non nul s'il reste des échecs : visible par un cron.
    return 0 if set(results) == {PayoutStatus.ENVOYE} else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Relance les versements en attente ou en échec.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Versements par passage.")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.limit)))


if __name__ == "__main__":
    main()
