"""Notifications push (Web Push) : configuration et abonnements des appareils.

Réservé aux comptes client et artisan (les participants de la messagerie).
L'envoi, lui, n'a pas de route : il est déclenché par l'enregistrement d'un
message (app/api/v1/conversations.py -> app/services/message_notifications.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.push import PushConfigOut, PushSubscriptionIn, PushUnsubscribeIn
from app.services import push_subscriptions as push_service
from app.services.rate_limit import RateLimiter, get_push_subscription_rate_limiter

router = APIRouter(prefix="/push", tags=["push"])

Participant = Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LimiterDep = Annotated[RateLimiter, Depends(get_push_subscription_rate_limiter)]


class TropDAbonnementsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop de demandes pour les notifications. Patientez un instant.",
            status_code=429,
        )


async def _enforce_budget(limiter: RateLimiter, *, user: User, settings: Settings) -> None:
    # Vérifié AVANT toute écriture : au-delà de la limite, rien n'est enregistré.
    if not await limiter.check(
        f"user:{user.id}",
        max_hits=settings.rate_limit_push_subscription_per_user_max,
        window_seconds=settings.rate_limit_push_subscription_per_user_window_seconds,
    ):
        raise TropDAbonnementsError()


@router.get("/config", response_model=PushConfigOut)
async def get_push_config(settings: SettingsDep, user: Participant) -> PushConfigOut:
    return push_service.push_config(settings)


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    payload: PushSubscriptionIn,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    limiter: LimiterDep,
) -> Response:
    await _enforce_budget(limiter, user=user, settings=settings)
    await push_service.subscribe(session, user=user, payload=payload, settings=settings)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: PushUnsubscribeIn,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    limiter: LimiterDep,
) -> Response:
    await _enforce_budget(limiter, user=user, settings=settings)
    await push_service.unsubscribe(session, user=user, endpoint=payload.endpoint)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
