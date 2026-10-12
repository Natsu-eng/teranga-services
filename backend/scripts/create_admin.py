"""CLI de bootstrap du premier admin (BUILD_PLAN.md, espace admin).

SEUL chemin vers le rôle `admin` : aucun endpoint, aucun paramètre d'API ne
l'attribue (`app.services.auth._SIGNUP_ROLES` verrouille explicitement
`{client, artisan}` à l'inscription, `app.api.deps` ne lit jamais `role`
depuis une requête entrante). Réservé à l'opérateur -- exige un accès
direct à la base (`DATABASE_URL`), jamais exposé sur le réseau, jamais
appelable depuis le frontend.

Promeut un utilisateur EXISTANT (déjà inscrit via le parcours OTP normal,
BUILD_PLAN.md §4) ; ne crée jamais de compte. Idempotent : relancer sur un
numéro déjà admin est un succès silencieux, pas une erreur.

Usage :
    uv run python scripts/create_admin.py +221771234567
    uv run python scripts/create_admin.py +221771234567 --yes   # sans confirmation interactive
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Exécuté comme un script de fichier (pas `python -m`) : Python met le
# dossier scripts/ sur sys.path, pas backend/. Sans ceci, `import app` échoue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.phone import PhoneInvalideError, normalize_phone  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from app.models.enums import AuditAction, AuditTargetType, Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import audit as audit_service  # noqa: E402


class AdminPromotionError(Exception):
    """Le numéro fourni ne correspond à aucun compte actif -- ce script ne
    crée jamais de compte, l'utilisateur doit d'abord s'inscrire normalement."""


async def promote_to_admin(session: AsyncSession, phone: str) -> tuple[User, bool]:
    """Promeut l'utilisateur au numéro E.164 `phone` au rôle admin.

    Renvoie `(user, already_admin)` -- `already_admin=True` signale un
    no-op idempotent (le compte était déjà admin), pas une erreur. Lève
    `AdminPromotionError` si aucun compte actif ne correspond à ce numéro.
    """
    stmt = select(User).where(User.phone == phone, User.deleted_at.is_(None))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise AdminPromotionError(
            f"Aucun compte actif avec le numéro {phone!r}. Ce script ne crée jamais de "
            "compte : l'utilisateur doit d'abord s'inscrire normalement (téléphone + OTP)."
        )
    if user.role is Role.ADMIN:
        return user, True

    previous_role = user.role
    user.role = Role.ADMIN
    await session.flush()
    # Journalisé comme toute promotion, sans acteur applicatif (script CLI).
    await audit_service.record(
        session,
        actor=None,
        action=AuditAction.ADMIN_BOOTSTRAP,
        target_type=AuditTargetType.USER,
        target_id=user.id,
        details={"previous_role": previous_role, "via": "scripts/create_admin.py"},
    )
    return user, False


async def _run(raw_phone: str, *, skip_confirmation: bool) -> int:
    settings = get_settings()
    try:
        phone = normalize_phone(raw_phone, settings)
    except PhoneInvalideError as exc:
        print(f"Erreur : {exc.message}", file=sys.stderr)
        return 1

    if not skip_confirmation:
        answer = input(f"Promouvoir {phone} au rôle admin ? [y/N] ").strip().lower()
        if answer != "y":
            print("Annulé.")
            return 0

    async with async_session_maker() as session, session.begin():
        try:
            user, already_admin = await promote_to_admin(session, phone)
        except AdminPromotionError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1

    if already_admin:
        print(f"{user.full_name} ({phone}) est déjà admin -- rien à faire.")
    else:
        print(f"{user.full_name} ({phone}) est maintenant admin.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promeut un utilisateur existant au rôle admin (BUILD_PLAN.md, espace admin)."
    )
    parser.add_argument("phone", help="Numéro de téléphone E.164 du compte à promouvoir")
    parser.add_argument(
        "--yes", action="store_true", help="Ignore la confirmation interactive (scripts/CI)."
    )
    args = parser.parse_args()

    exit_code = asyncio.run(_run(args.phone, skip_confirmation=args.yes))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
