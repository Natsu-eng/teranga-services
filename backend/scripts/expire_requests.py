"""Expiration des demandes restées ouvertes trop longtemps (sans artisan).

La règle (REQUEST_OPEN_TTL_DAYS, 30 jours par défaut) s'applique DÉJÀ
d'office : une demande périmée est affichée « expirée », n'est plus
proposée aux artisans et ne peut plus être envoyée, même si ce script n'a
jamais tourné. Il ENREGISTRE ce statut en base (statistiques, requêtes
directes). Idempotent ; une demande mise en relation entre-temps n'est
jamais touchée. À planifier une fois par jour (cron).

Usage :
    uv run python scripts/expire_requests.py
"""

import asyncio
import sys
from pathlib import Path

# Exécuté comme un script de fichier (pas `python -m`) : Python met le
# dossier scripts/ sur sys.path, pas backend/. Sans ceci, `import app` échoue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from app.services import requests as requests_service  # noqa: E402


async def _run() -> int:
    settings = get_settings()
    async with async_session_maker() as session, session.begin():
        count = await requests_service.expire_stale_requests(session, settings=settings)
    print(
        f"{count} demande(s) expirée(s) (ouvertes depuis plus de "
        f"{settings.request_open_ttl_days} jours)."
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
