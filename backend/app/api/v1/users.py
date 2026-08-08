"""Endpoints /api/v1/users (BUILD_PLAN.md, fix confidentialité du contact).

Rôle-agnostique par construction : `require_role` n'est volontairement pas
utilisé ici, seule l'authentification l'est (`get_current_user`) -- un
client comme un artisan éditent leur propre nom par ce même endpoint.
L'édition étendue du profil artisan (bio, métiers, documents) reste sur
`PATCH /artisans/me` (`app/api/v1/artisans.py`), qui accepte aussi
`full_name` pour ne pas forcer l'artisan à connaître deux endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.users import UserProfileUpdateIn
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserOut)
async def update_my_profile(
    payload: UserProfileUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    result = await users_service.update_full_name(
        session, user=user, raw_full_name=payload.full_name
    )
    await session.commit()
    return result
