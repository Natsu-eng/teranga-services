"""Endpoints /api/v1/interventions (BUILD_PLAN.md §3.2, §6 Lot 12).

Routes seules : toute la logique métier (règles d'engagement, résolution et
figeage du taux de commission, autorisation) vit dans
`app.services.interventions`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.interventions import InterventionCreateIn, InterventionOut
from app.schemas.pagination import Page
from app.services import interventions as interventions_service

router = APIRouter(prefix="/interventions", tags=["interventions"])


@router.post("", response_model=InterventionOut, status_code=status.HTTP_201_CREATED)
async def create_intervention(
    payload: InterventionCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> InterventionOut:
    result = await interventions_service.create_intervention(
        session, client=client, payload=payload, settings=settings
    )
    await session.commit()
    return result


@router.get("/me", response_model=Page[InterventionOut])
async def list_my_interventions(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[InterventionOut]:
    return await interventions_service.list_my_interventions(
        session,
        user=user,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/{intervention_id}", response_model=InterventionOut)
async def get_intervention(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> InterventionOut:
    return await interventions_service.get_intervention_for_user(
        session, intervention_id=intervention_id, user=user
    )
