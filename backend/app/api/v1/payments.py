"""Endpoints /api/v1/payments et /api/v1/webhooks/payments (BUILD_PLAN.md §3.5).

Routes seules : toute la logique (montant serveur, séquestre, idempotence
des webhooks) vit dans `app.services.payments`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider, require_role
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.pagination import Page
from app.schemas.payments import (
    ArtisanEarningsOut,
    ClientPaymentOut,
    PaymentInitIn,
    PaymentOptionsOut,
    PaymentSummaryOut,
    PayoutSettingsIn,
    PayoutSettingsOut,
)
from app.services import payment_queries as payment_queries_service
from app.services import payments as payments_service
from app.services import payouts as payouts_service
from app.services.payment_providers.base import PaymentProvider
from app.services.rate_limit import RateLimiter, get_payment_init_rate_limiter

router = APIRouter(prefix="/payments", tags=["payments"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ProviderDep = Annotated[PaymentProvider | None, Depends(get_payment_provider)]


class WebhookTropVolumineuxError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_TROP_VOLUMINEUX",
            message="Notification trop volumineuse.",
            status_code=413,
        )


async def _read_bounded_body(request: Request, max_bytes: int) -> bytes:
    """Corps brut (la signature porte sur les octets exacts), lu par morceaux
    et abandonné dès qu'il dépasse `max_bytes`."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise WebhookTropVolumineuxError()
        chunks.append(chunk)
    return b"".join(chunks)


class TropDeTentativesDePaiementError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop de tentatives de paiement. Patientez quelques minutes.",
            status_code=429,
        )


@router.get("/options", response_model=PaymentOptionsOut)
async def get_payment_options(
    settings: SettingsDep,
    provider: ProviderDep,
    # Client (moyens proposés au paiement) ET artisan (écran des gains : en
    # mode espèces, pas de versement ni de séquestre à montrer). Réponse de
    # configuration seule, identique pour tous : aucune donnée personnelle.
    _user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
) -> PaymentOptionsOut:
    return payments_service.get_options(settings, provider)


@router.post("/init", response_model=PaymentSummaryOut)
async def init_payment(
    payload: PaymentInitIn,
    session: SessionDep,
    settings: SettingsDep,
    provider: ProviderDep,
    limiter: Annotated[RateLimiter, Depends(get_payment_init_rate_limiter)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> PaymentSummaryOut:
    if not await limiter.check(
        f"user:{client.id}",
        max_hits=settings.rate_limit_payment_init_per_user_max,
        window_seconds=settings.rate_limit_payment_init_per_user_window_seconds,
    ):
        raise TropDeTentativesDePaiementError()
    result = await payments_service.init_payment(
        session, user=client, payload=payload, settings=settings, provider=provider
    )
    await session.commit()
    return result


@router.get("/me", response_model=Page[ClientPaymentOut])
async def list_my_payments(
    session: SessionDep,
    settings: SettingsDep,
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ClientPaymentOut]:
    return await payment_queries_service.list_client_payments(
        session,
        user=client,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/me/earnings", response_model=ArtisanEarningsOut)
async def get_my_earnings(
    session: SessionDep,
    settings: SettingsDep,
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> ArtisanEarningsOut:
    return await payment_queries_service.artisan_earnings(
        session,
        user=artisan,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/me/payout-settings", response_model=PayoutSettingsOut)
async def get_my_payout_settings(
    session: SessionDep,
    settings: SettingsDep,
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> PayoutSettingsOut:
    return await payouts_service.get_payout_settings(session, user=artisan, settings=settings)


@router.put("/me/payout-settings", response_model=PayoutSettingsOut)
async def set_my_payout_settings(
    payload: PayoutSettingsIn,
    session: SessionDep,
    settings: SettingsDep,
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> PayoutSettingsOut:
    result = await payouts_service.set_payout_settings(
        session, user=artisan, payload=payload, settings=settings
    )
    await session.commit()
    return result


@webhooks_router.post("/payments")
async def receive_payment_webhook(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: ProviderDep,
) -> dict[str, str]:
    """Public (le fournisseur n'a pas de compte) mais AUTHENTIFIÉ par la
    signature HMAC du corps brut, vérifiée avant toute lecture. 200 pour
    tout événement accepté, déjà traité ou ignoré -- le fournisseur cesse
    alors ses tentatives ; 401/400 sinon, sans rien écrire."""
    payload = await _read_bounded_body(request, settings.payment_webhook_max_body_bytes)
    outcome = await payments_service.handle_webhook(
        session,
        provider=provider,
        payload=payload,
        headers=dict(request.headers),
        settings=settings,
    )
    await session.commit()
    return {"status": outcome}
