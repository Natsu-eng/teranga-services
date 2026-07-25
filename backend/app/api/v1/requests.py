"""Endpoints /api/v1/requests (BUILD_PLAN.md §3.2, §6 Lot 12).

Routes seules : toute la logique métier (validation du métier, re-validation
de l'estimation IA, autorisation) vit dans `app.services.requests`.
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
from app.schemas.pagination import Page
from app.schemas.requests import ServiceRequestCreateIn, ServiceRequestOut
from app.services import requests as requests_service

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=ServiceRequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: ServiceRequestCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> ServiceRequestOut:
    result = await requests_service.create_request(session, client=client, payload=payload)
    await session.commit()
    return result


@router.get("/me", response_model=Page[ServiceRequestOut])
async def list_my_requests(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ServiceRequestOut]:
    return await requests_service.list_my_requests(
        session,
        client=client,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/{request_id}", response_model=ServiceRequestOut)
async def get_request(
    request_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ServiceRequestOut:
    return await requests_service.get_request_for_user(session, request_id=request_id, user=user)
