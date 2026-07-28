"""Endpoints /api/v1/auth (BUILD_PLAN.md §3.2, §4).

Sécurité par construction : `request-otp` ne branche jamais sur
l'existence d'un compte (voir `app.services.otp.request_otp`), ce qui rend
sa réponse non énumérante -- toujours 204, délai d'exécution identique que
le numéro corresponde à un compte existant ou non.

**Commit explicite même sur échec applicatif** : plusieurs échecs "normaux"
(mauvais code OTP, rejeu d'un refresh révoqué…) mutent quand même l'état en
base (compteur `attempts`, révocation de famille) -- ces effets doivent
être persistés même quand l'endpoint répond une erreur, sinon le rollback
implicite de fin de requête les annulerait et viderait de son sens le
compteur anti-bruteforce ou la révocation de famille en cas de vol détecté.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import (
    AuthResponseOut,
    RefreshIn,
    RequestOtpIn,
    TokenPairOut,
    UserOut,
    VerifyOtpIn,
)
from app.services import auth as auth_service
from app.services import otp as otp_service
from app.services.rate_limit import SlidingWindowRateLimiter, get_otp_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class TropDeDemandesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop de demandes, merci de réessayer plus tard.",
            status_code=429,
        )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/request-otp", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(
    payload: RequestOtpIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[SlidingWindowRateLimiter, Depends(get_otp_rate_limiter)],
) -> Response:
    phone = normalize_phone(payload.phone, settings)

    phone_ok = await rate_limiter.check(
        f"phone:{phone}",
        max_hits=settings.rate_limit_otp_per_phone_max,
        window_seconds=settings.rate_limit_otp_per_phone_window_seconds,
    )
    ip_ok = await rate_limiter.check(
        f"ip:{_client_ip(request)}",
        max_hits=settings.rate_limit_otp_per_ip_max,
        window_seconds=settings.rate_limit_otp_per_ip_window_seconds,
    )
    if not (phone_ok and ip_ok):
        raise TropDeDemandesError()

    await otp_service.request_otp(session, phone, settings=settings)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-otp", response_model=AuthResponseOut)
async def verify_otp(
    payload: VerifyOtpIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponseOut:
    try:
        phone = await otp_service.verify_otp(
            session, payload.phone, payload.code, settings=settings
        )
    except AppError:
        # Persiste l'effet de bord de la tentative ratée (compteur
        # `attempts` incrémenté, code invalidé au seuil) avant de rejeter.
        await session.commit()
        raise

    try:
        user = await auth_service.resolve_account_for_intent(
            session, phone, intent=payload.intent, role=payload.role
        )
    except AppError:
        # Idem : un rejet ici (rôle invalide, compte déjà existant / inexistant)
        # ne doit pas annuler les effets de bord déjà actés par l'OTP ci-dessus
        # (code consommé, compteur d'attempts).
        await session.commit()
        raise

    access, refresh = await auth_service.issue_token_pair(
        session,
        user,
        settings=settings,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    user_out = await auth_service.to_user_out(session, user)
    await session.commit()
    return AuthResponseOut(access=access, refresh=refresh, user=user_out)


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(
    payload: RefreshIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairOut:
    try:
        access, refresh_token = await auth_service.rotate_refresh_token(
            session,
            payload.refresh,
            settings=settings,
            user_agent=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    except AppError:
        # Persiste la révocation (rotation normale, ou révocation de
        # famille en cas de rejeu détecté) même quand la requête échoue.
        await session.commit()
        raise
    await session.commit()
    return TokenPairOut(access=access, refresh=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    await auth_service.revoke_refresh_token(session, payload.refresh, settings=settings)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await auth_service.revoke_all_sessions(session, user.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    return await auth_service.to_user_out(session, user)
