from fastapi import APIRouter

from app.api.v1 import ai, artisans, auth, health, interventions, requests, trades

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(artisans.router)
router.include_router(trades.router)
router.include_router(ai.router)
router.include_router(requests.router)
router.include_router(interventions.router)
