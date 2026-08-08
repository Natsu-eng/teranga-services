"""Édition du compte utilisateur, rôle-agnostique (BUILD_PLAN.md, fix
confidentialité du contact). Contrairement à `app.services.artisans`
(profil artisan étendu -- bio, métiers, documents), ce module ne connaît
que le socle commun aux deux rôles : pour l'instant, uniquement `full_name`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.full_name import validate_full_name
from app.models.user import User
from app.schemas.auth import UserOut
from app.services.auth import to_user_out


async def update_full_name(session: AsyncSession, *, user: User, raw_full_name: str) -> UserOut:
    """Édite le nom du compte COURANT (résolu depuis le token, jamais un id
    reçu du client -- même principe que `app.services.artisans.get_own_profile`) :
    aucun endpoint ne permet d'éditer le nom d'un tiers."""
    user.full_name = validate_full_name(raw_full_name)
    await session.flush()
    return await to_user_out(session, user)
