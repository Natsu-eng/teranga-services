from fastapi import APIRouter

from app.api.v1 import artisans, auth, health, trades

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(artisans.router)
router.include_router(trades.router)
