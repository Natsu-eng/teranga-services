"""Validation métier de list_artisans (BUILD_PLAN.md §5, §6 Lot 9) -- sans HTTP."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.artisans import ArtisanSort
from app.schemas.artisans import ArtisanListItemOut
from app.schemas.pagination import Page
from app.services.artisan_errors import (
    PageHorsBornesError,
    PositionInvalideError,
    RayonRechercheInvalideError,
    TriDistanceSansPositionError,
)
from app.services.artisans import list_artisans

SETTINGS = get_settings()


async def _list(db_session: AsyncSession, **overrides: Any) -> Page[ArtisanListItemOut]:
    params: dict[str, Any] = {
        "trade": None,
        "near": None,
        "radius_m": None,
        "min_rating": None,
        "available": None,
        "q": None,
        "sort": None,
        "page": 1,
        "page_size": 20,
        "settings": SETTINGS,
    }
    params.update(overrides)
    return await list_artisans(db_session, **params)


@pytest.mark.parametrize("raw", ["abc", "14.5", "1000,50", "14.5,-500", "14.5,-17.4,999"])
async def test_invalid_near_is_rejected(db_session: AsyncSession, raw: str) -> None:
    with pytest.raises(PositionInvalideError):
        await _list(db_session, near=raw)


async def test_radius_zero_or_negative_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(RayonRechercheInvalideError):
        await _list(db_session, near="14.6937,-17.4441", radius_m=0)


async def test_radius_above_max_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(RayonRechercheInvalideError):
        await _list(
            db_session, near="14.6937,-17.4441", radius_m=SETTINGS.artisan_search_max_radius_m + 1
        )


async def test_radius_defaults_when_not_provided(db_session: AsyncSession) -> None:
    page = await _list(db_session, near="14.6937,-17.4441")  # radius_m omis

    assert page.pagination.page == 1  # ne lève pas, utilise le défaut Settings


async def test_sort_distance_without_near_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(TriDistanceSansPositionError):
        await _list(db_session, sort="distance")


async def test_near_without_explicit_sort_defaults_to_distance_without_error(
    db_session: AsyncSession,
) -> None:
    page = await _list(db_session, near="14.6937,-17.4441", radius_m=10_000)

    assert page.pagination.page == 1


async def test_absent_near_defaults_to_rating_sort_without_error(db_session: AsyncSession) -> None:
    page = await _list(db_session)  # ni near, ni sort

    assert page.pagination.page == 1


@pytest.mark.parametrize("sort", ["distance", "rating", "recent"])
async def test_all_sort_modes_accepted_when_valid(
    db_session: AsyncSession, sort: ArtisanSort
) -> None:
    near = "14.6937,-17.4441" if sort == "distance" else None
    page = await _list(db_session, near=near, radius_m=10_000, sort=sort)

    assert page.pagination.page == 1


async def test_page_beyond_hard_cap_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(PageHorsBornesError):
        await _list(db_session, page=SETTINGS.pagination_max_page + 1)


async def test_page_beyond_actual_results_returns_empty_but_valid(
    db_session: AsyncSession,
) -> None:
    page = await _list(db_session, trade="un-metier-qui-nexiste-pas-xyz", page=3, page_size=5)

    assert page.items == []
    assert page.pagination.page == 3
    assert page.pagination.total == 0


async def test_page_size_above_max_is_silently_clamped(db_session: AsyncSession) -> None:
    page = await _list(db_session, page_size=SETTINGS.pagination_page_size_max + 100)

    assert page.pagination.page_size == SETTINGS.pagination_page_size_max
