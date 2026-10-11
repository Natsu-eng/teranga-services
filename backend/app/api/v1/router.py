from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai,
    artisans,
    auth,
    conversations,
    health,
    interventions,
    realtime,
    requests,
    trades,
    users,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(artisans.router)
router.include_router(trades.router)
router.include_router(ai.router)
router.include_router(requests.router)
router.include_router(interventions.router)
router.include_router(conversations.router)
router.include_router(realtime.router)
router.include_router(admin.router)
