"""Endpoint /api/v1/meta : informations publiques sur l'instance.

Lecture publique, sans authentification : sert au front à savoir s'il tourne
sur une instance de test (bandeau « Version de test », transparence beta).
N'expose qu'un environnement et un booléen, jamais un réglage secret.
`/meta/neighborhoods` publie la liste fermée des quartiers desservis
(données OpenStreetMap publiques) et la région desservie.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.neighborhoods import (
    DEFAULT_NEIGHBORHOOD_ID,
    DEPARTMENT_LABELS,
    LEGACY_ALIASES,
    NEIGHBORHOODS,
)
from app.schemas.meta import MetaOut, NeighborhoodOut, NeighborhoodsOut, ServiceRegionOut
from app.services.otp_test_mode import is_test_mode_enabled

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("", response_model=MetaOut)
async def instance_meta(settings: Annotated[Settings, Depends(get_settings)]) -> MetaOut:
    return MetaOut(
        environment=settings.environment,
        otp_test_mode=is_test_mode_enabled(settings),
    )


@router.get("/neighborhoods", response_model=NeighborhoodsOut)
async def neighborhoods(settings: Annotated[Settings, Depends(get_settings)]) -> NeighborhoodsOut:
    return NeighborhoodsOut(
        items=[
            NeighborhoodOut(
                id=n.id,
                label=n.label,
                commune=n.osm_name,
                department=n.department.value,
                department_label=DEPARTMENT_LABELS[n.department],
                lat=n.lat,
                lng=n.lng,
            )
            for n in NEIGHBORHOODS
        ],
        aliases=dict(LEGACY_ALIASES),
        default_id=DEFAULT_NEIGHBORHOOD_ID,
        service_region=ServiceRegionOut(
            center_lat=settings.service_region_center_lat,
            center_lng=settings.service_region_center_lng,
            radius_m=settings.service_region_radius_m,
        ),
    )
