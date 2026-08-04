"""Tests du script de bootstrap admin (BUILD_PLAN.md, espace admin) --
`scripts/create_admin.py` est le SEUL chemin vers le rôle admin, jamais un
endpoint. Teste `promote_to_admin` directement (la fonction testable
derrière le CLI), pas le point d'entrée `main()` (parsing argv, `input()`
interactif) -- hors périmètre utile pour un test unitaire.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.models.user import User
from scripts.create_admin import AdminPromotionError, promote_to_admin
from tests.factories import make_user


async def test_promotes_an_existing_user_to_admin(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT, full_name="Future Admin")

    promoted, already_admin = await promote_to_admin(db_session, user.phone)

    assert already_admin is False
    assert promoted.id == user.id
    stmt = select(User.role).where(User.id == user.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == Role.ADMIN


async def test_promotes_an_artisan_to_admin_too(db_session: AsyncSession) -> None:
    """Aucune restriction de rôle de départ -- un client comme un artisan
    peuvent être promus, seul un compte existant est exigé."""
    user = await make_user(db_session, role=Role.ARTISAN)

    promoted, already_admin = await promote_to_admin(db_session, user.phone)

    assert already_admin is False
    assert promoted.role is Role.ADMIN


async def test_promoting_an_already_admin_user_is_idempotent(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    await promote_to_admin(db_session, user.phone)

    promoted_again, already_admin = await promote_to_admin(db_session, user.phone)

    assert already_admin is True
    assert promoted_again.role is Role.ADMIN


async def test_refuses_a_phone_number_with_no_account(db_session: AsyncSession) -> None:
    unknown_phone = f"+22177{uuid.uuid4().int % 10**7:07d}"

    # `match=` ferait de `unknown_phone` un motif regex -- son "+" initial
    # (quantificateur en regex) le casserait, d'où une comparaison directe.
    with pytest.raises(AdminPromotionError) as exc_info:
        await promote_to_admin(db_session, unknown_phone)
    assert unknown_phone in str(exc_info.value)


async def test_refuses_a_soft_deleted_account(db_session: AsyncSession) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    user.deleted_at = datetime.now(UTC)
    await db_session.flush()

    with pytest.raises(AdminPromotionError):
        await promote_to_admin(db_session, user.phone)
