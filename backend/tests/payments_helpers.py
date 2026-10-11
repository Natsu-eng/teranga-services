"""Outils partagés des tests de paiement (BUILD_PLAN.md §3.5).

L'application réelle est exercée en ASGI (routes, dépendances, fournisseur
sandbox), sur la session transactionnelle du test : rien n'est jamais
écrit durablement dans la base de dev.
"""

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.enums import InterventionStatus, QuoteStatus
from app.models.payment import Payment, PaymentEvent, Payout, PlatformFee
from app.models.user import User
from app.services.payment_providers import resolve_webhook_secret
from app.services.payment_providers.sandbox import (
    EVENT_COMPLETED,
    SIGNATURE_HEADER,
    sign_payload,
)
from tests.factories import Engagement, make_engagement, make_quote

AMOUNT = 12_000  # devis par défaut : 8 000 main d'œuvre + 4 000 matériaux
COMMISSION = 1_200  # 10 % (taux figé par make_engagement)
NET = AMOUNT - COMMISSION


@contextmanager
def override_dependencies(db_session: AsyncSession, **settings_changes: Any) -> Iterator[None]:
    """Session du test pour les routes ET pour les transactions ouvertes
    après le commit (envoi du versement)."""

    async def _get_test_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    @asynccontextmanager
    async def _test_session_scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    settings = get_settings().model_copy(update=settings_changes)
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_session_factory] = lambda: _test_session_scope
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def current_settings() -> Settings:
    override = app.dependency_overrides.get(get_settings)
    return override() if override is not None else get_settings()


def update_settings(**changes: Any) -> None:
    settings = current_settings().model_copy(update=changes)
    app.dependency_overrides[get_settings] = lambda: settings


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def make_payable_engagement(
    session: AsyncSession, *, labor_fcfa: int = 8_000, materials_fcfa: int = 4_000
) -> Engagement:
    """Intervention `en_cours` dont le devis est accepté : le paiement est
    exigible, pour `labor_fcfa + materials_fcfa`."""
    engagement = await make_engagement(session, status=InterventionStatus.EN_COURS)
    await make_quote(
        session,
        intervention=engagement.intervention,
        labor_fcfa=labor_fcfa,
        materials_fcfa=materials_fcfa,
        status=QuoteStatus.ACCEPTE,
    )
    engagement.intervention.agreed_amount_fcfa = labor_fcfa + materials_fcfa
    await session.flush()
    return engagement


async def init_payment(http: AsyncClient, engagement: Engagement, channel: str) -> Response:
    return await http.post(
        "/api/v1/payments/init",
        json={"intervention_id": str(engagement.intervention.id), "channel": channel},
        headers=auth(engagement.client),
    )


def event_body(
    payment: Payment,
    *,
    event_type: str = EVENT_COMPLETED,
    amount: int | None = None,
    event_id: str | None = None,
) -> bytes:
    """Notification au format du sandbox pour ce paiement."""
    return json.dumps(
        {
            "id": event_id or f"EV_{uuid.uuid4().hex}",
            "type": event_type,
            "data": {
                "id": payment.provider_ref,
                "amount": str(payment.amount_fcfa if amount is None else amount),
                "currency": "XOF",
            },
        }
    ).encode()


async def post_webhook(http: AsyncClient, body: bytes, *, signature: str | None = None) -> Response:
    """Livre `body` au webhook, signé avec le secret configuré (ou la
    signature fournie)."""
    header = signature or sign_payload(resolve_webhook_secret(current_settings()), body)
    return await http.post(
        "/api/v1/webhooks/payments",
        content=body,
        headers={"Content-Type": "application/json", SIGNATURE_HEADER: header},
    )


async def only_payment(session: AsyncSession, engagement: Engagement) -> Payment:
    payments = await payments_of(session, engagement)
    assert len(payments) == 1, payments
    return payments[0]


async def payments_of(session: AsyncSession, engagement: Engagement) -> list[Payment]:
    stmt = (
        select(Payment)
        .where(Payment.intervention_id == engagement.intervention.id)
        .order_by(Payment.created_at)
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).scalars().all())


async def commission_of(session: AsyncSession, engagement: Engagement) -> PlatformFee | None:
    stmt = (
        select(PlatformFee)
        .where(PlatformFee.intervention_id == engagement.intervention.id)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def payouts_of(session: AsyncSession, engagement: Engagement) -> list[Payout]:
    stmt = (
        select(Payout)
        .where(Payout.intervention_id == engagement.intervention.id)
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_events(session: AsyncSession, event_id: str) -> int:
    stmt = select(func.count()).select_from(PaymentEvent).where(PaymentEvent.event_id == event_id)
    return (await session.execute(stmt)).scalar_one()


async def pay_online(http: AsyncClient, session: AsyncSession, engagement: Engagement) -> Payment:
    """Paiement en ligne complet : checkout ouvert puis webhook de succès ->
    fonds retenus (séquestre)."""
    response = await init_payment(http, engagement, "wave")
    assert response.status_code == 200, response.text
    payment = await only_payment(session, engagement)
    webhook = await post_webhook(http, event_body(payment))
    assert webhook.json() == {"status": "retenu"}, webhook.text
    return payment
