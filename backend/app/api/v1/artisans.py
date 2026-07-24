"""Endpoints /api/v1/artisans (BUILD_PLAN.md §3.2, §5, §6 Lot 9).

Routes seules : extraction/validation superficielle des query params (types,
bornes triviales déléguées à FastAPI/Pydantic), toute la logique métier
(parsing de `near`, résolution du tri/rayon, plafond dur de pagination) vit
dans `app.services.artisans`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.repositories.artisans import ArtisanSort
from app.schemas.artisans import ArtisanListItemOut
from app.schemas.pagination import Page
from app.services import artisans as artisans_service

router = APIRouter(prefix="/artisans", tags=["artisans"])


@router.get("", response_model=Page[ArtisanListItemOut])
async def list_artisans(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    trade: Annotated[str | None, Query(description="Code du métier")] = None,
    near: Annotated[str | None, Query(description="Position du client, format lat,lng")] = None,
    radius_m: Annotated[
        int | None, Query(gt=0, description="Rayon de recherche, en mètres")
    ] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    available: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(description="Recherche libre sur le nom et la bio")] = None,
    sort: Annotated[ArtisanSort | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ArtisanListItemOut]:
    return await artisans_service.list_artisans(
        session,
        trade=trade,
        near=near,
        radius_m=radius_m,
        min_rating=min_rating,
        available=available,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )
