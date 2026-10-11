"""Séquestre : complétion -> versement, annulation -> remboursement, litige
-> arbitrage (BUILD_PLAN.md §3.5)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider
from app.api.v1.sandbox import WebhookDeliverer, get_webhook_deliverer
from app.db.session import get_session_factory
from app.main import app
from app.models.enums import (
    InterventionStatus,
    PaymentStatus,
    PayoutChannel,
    PayoutStatus,
    PlatformFeeStatus,
    Role,
    ServiceRequestStatus,
)
from app.models.request import ServiceRequest
from app.models.user import User
from app.services import payments as payments_service
from app.services.payment_providers.base import (
    PaymentProviderError,
    PayoutRequest,
    ProviderOperation,
    RefundRequest,
)
from app.services.payment_providers.sandbox import SandboxProvider
from tests.factories import Engagement, make_engagement, make_user
from tests.payments_helpers import (
    AMOUNT,
    COMMISSION,
    NET,
    auth,
    client,
    commission_of,
    current_settings,
    init_payment,
    make_payable_engagement,
    only_payment,
    override_dependencies,
    pay_online,
    payouts_of,
)


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession) -> Iterator[None]:
    with override_dependencies(db_session):
        yield


def _sandbox() -> SandboxProvider:
    provider = app.dependency_overrides.get(get_payment_provider)
    if provider is not None:
        built = provider()
        assert isinstance(built, SandboxProvider)
        return built
    from app.services.payment_providers import build_payment_provider

    built = build_payment_provider(current_settings())
    assert isinstance(built, SandboxProvider)
    return built


class _BrokenOperations(SandboxProvider):
    """Sandbox dont les remboursements et versements échouent (panne)."""

    async def refund(self, request: RefundRequest) -> ProviderOperation:
        raise PaymentProviderError("remboursements indisponibles")

    async def send_payout(self, request: PayoutRequest) -> ProviderOperation:
        raise PaymentProviderError("versements indisponibles")


def _break_operations() -> None:
    from app.services.payment_providers import resolve_webhook_secret

    settings = current_settings()
    broken = _BrokenOperations(
        webhook_secret=resolve_webhook_secret(settings),
        checkout_base_url=settings.backend_public_base_url,
        tolerance_seconds=settings.payment_webhook_tolerance_seconds,
    )
    app.dependency_overrides[get_payment_provider] = lambda: broken


async def _complete(http: AsyncClient, engagement: Engagement) -> Response:
    return await http.post(
        f"/api/v1/interventions/{engagement.intervention.id}/complete",
        headers=auth(engagement.client),
    )


# ------------------------------------------------------------------ complétion


async def test_completion_releases_escrow_and_pays_the_net_to_the_artisan(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        response = await _complete(http, engagement)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "terminee"
    assert body["payment"]["status"] == "libere"
    assert body["payment"]["net_fcfa"] == NET
    assert body["payment"]["commission"] == {
        "rate_bps": 1000,
        "amount_fcfa": COMMISSION,
        "status": "collectee",
    }
    assert body["payment"]["payout"]["status"] == "envoye"
    assert body["payment"]["payout"]["amount_fcfa"] == NET

    payment = await only_payment(db_session, engagement)
    assert payment.status is PaymentStatus.LIBERE
    assert payment.released_at is not None
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.COLLECTEE
    (payout,) = await payouts_of(db_session, engagement)
    assert payout.amount_fcfa == NET
    assert payout.amount_fcfa + fee.amount_fcfa == AMOUNT
    assert payout.status is PayoutStatus.ENVOYE
    assert payout.channel is PayoutChannel.WAVE
    # Toujours vers le numéro vérifié du compte artisan.
    assert payout.destination_phone == engagement.artisan_user.phone


async def test_the_payout_uses_the_channel_chosen_by_the_artisan(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    engagement.artisan.payout_channel = PayoutChannel.ORANGE_MONEY
    await db_session.flush()

    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _complete(http, engagement)

    (payout,) = await payouts_of(db_session, engagement)
    assert payout.channel is PayoutChannel.ORANGE_MONEY


async def test_completion_with_cash_leaves_the_commission_due(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "cash")
        response = await _complete(http, engagement)

    assert response.status_code == 200
    assert response.json()["payment"]["status"] == "reussi"
    assert await payouts_of(db_session, engagement) == []
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.DUE
    assert fee.amount_fcfa == COMMISSION


async def test_completion_without_any_payment_is_measured_as_commission_due(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await _complete(http, engagement)

    assert response.status_code == 200
    assert response.json()["payment"]["status"] is None
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.DUE


async def test_completion_waits_for_an_open_checkout(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        response = await _complete(http, engagement)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAIEMENT_EN_COURS"
    await db_session.rollback()


async def test_a_payout_outage_never_blocks_completion_and_can_be_retried(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        _break_operations()
        response = await _complete(http, engagement)

    assert response.status_code == 200
    assert response.json()["status"] == "terminee"
    assert response.json()["payment"]["payout"]["status"] == "echoue"
    (payout,) = await payouts_of(db_session, engagement)
    assert payout.status is PayoutStatus.ECHOUE
    assert payout.attempts == 1
    assert payout.failure_reason

    # Le fournisseur revient : la relance verse, une seule fois.
    app.dependency_overrides.pop(get_payment_provider)
    results = await payments_service.dispatch_pending_payouts(
        app.dependency_overrides[get_session_factory](),
        provider=_sandbox(),
        settings=current_settings(),
        limit=10,
    )
    assert results.get(PayoutStatus.ENVOYE, 0) >= 1
    (payout,) = await payouts_of(db_session, engagement)
    assert payout.status is PayoutStatus.ENVOYE
    assert payout.attempts == 2
    assert payout.sent_at is not None


# ------------------------------------------------------------------ annulation


async def test_an_artisan_cancellation_refunds_the_client(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={"reason": "Pièce introuvable."},
            headers=auth(engagement.artisan_user),
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "annulee"
    assert body["cancellation"]["kind"] == "annulation"
    assert body["cancellation"]["by"] == "artisan"
    assert body["payment"]["status"] == "rembourse"
    payment = await only_payment(db_session, engagement)
    assert payment.status is PaymentStatus.REMBOURSE
    assert payment.refunded_at is not None and payment.refund_ref is not None
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE
    assert await payouts_of(db_session, engagement) == []
    request = await db_session.get(ServiceRequest, engagement.intervention.service_request_id)
    assert request is not None and request.status is ServiceRequestStatus.OUVERTE


async def test_a_client_cannot_cancel_alone_once_funds_are_held(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={},
            headers=auth(engagement.client),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANNULATION_FONDS_RETENUS"
    await db_session.rollback()


async def test_a_client_cancellation_voids_an_open_checkout(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={},
            headers=auth(engagement.client),
        )

    assert response.status_code == 200
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.ANNULE
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE


async def test_a_cancellation_voids_declared_cash(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "cash")
        await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={},
            headers=auth(engagement.client),
        )

    assert (await only_payment(db_session, engagement)).status is PaymentStatus.ANNULE
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE


async def test_who_can_cancel_when(db_session: AsyncSession) -> None:
    proposed = await make_engagement(db_session, status=InterventionStatus.PROPOSEE)
    accepted = await make_engagement(db_session, status=InterventionStatus.ACCEPTEE)
    done = await make_engagement(db_session, status=InterventionStatus.TERMINEE)
    outsider = await make_user(db_session, role=Role.CLIENT)

    async with client() as http:

        async def cancel(engagement: Engagement, user: User) -> Response:
            return await http.post(
                f"/api/v1/interventions/{engagement.intervention.id}/cancel",
                json={},
                headers=auth(user),
            )

        # Avant acceptation, l'artisan « refuse » (route dédiée), il n'annule pas.
        artisan_on_proposed = await cancel(proposed, proposed.artisan_user)
        client_on_proposed = await cancel(proposed, proposed.client)
        artisan_on_accepted = await cancel(accepted, accepted.artisan_user)
        on_done = await cancel(done, done.client)
        third_party = await cancel(accepted, outsider)

    assert artisan_on_proposed.status_code == 409
    assert client_on_proposed.status_code == 200
    assert client_on_proposed.json()["cancellation"]["by"] == "client"
    assert artisan_on_accepted.status_code == 200
    assert on_done.status_code == 409
    assert third_party.status_code in (403, 409)


async def test_a_refund_outage_changes_nothing(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        _break_operations()
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={},
            headers=auth(engagement.artisan_user),
        )

    assert response.status_code == 502
    await db_session.rollback()


# ------------------------------------------------------------------ litige


async def _open_dispute(http: AsyncClient, engagement: Engagement, user: User) -> Response:
    return await http.post(
        f"/api/v1/interventions/{engagement.intervention.id}/dispute",
        json={"reason": "Les travaux ne sont pas terminés."},
        headers=auth(user),
    )


async def test_a_dispute_freezes_the_escrow(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        opened = await _open_dispute(http, engagement, engagement.client)
        complete = await _complete(http, engagement)
        cancel = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={},
            headers=auth(engagement.artisan_user),
        )

    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "litige"
    assert opened.json()["dispute"]["opened_by"] == "client"
    assert complete.status_code == 409
    assert cancel.status_code == 409
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.RETENU
    assert await payouts_of(db_session, engagement) == []


async def test_an_artisan_can_open_a_dispute_when_the_client_never_confirms(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        response = await _open_dispute(http, engagement, engagement.artisan_user)

    assert response.status_code == 200
    assert response.json()["dispute"]["opened_by"] == "artisan"


async def test_a_dispute_needs_an_explanation(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/dispute",
            json={"reason": "Non."},
            headers=auth(engagement.client),
        )

    assert response.status_code == 422


async def _resolve(http: AsyncClient, engagement: Engagement, user: User, outcome: str) -> Response:
    return await http.post(
        f"/api/v1/admin/disputes/{engagement.intervention.id}/resolve",
        json={"outcome": outcome, "note": "Photos et échanges examinés."},
        headers=auth(user),
    )


async def test_an_admin_releasing_a_dispute_pays_the_artisan(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _open_dispute(http, engagement, engagement.artisan_user)
        queue = await http.get("/api/v1/admin/disputes", headers=auth(admin))
        response = await _resolve(http, engagement, admin, "libere")
        resolved = await http.get("/api/v1/admin/disputes?resolved=true", headers=auth(admin))

    assert str(engagement.intervention.id) in [item["id"] for item in queue.json()["items"]]
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "terminee"
    assert body["dispute"]["outcome"] == "libere"
    assert body["payment"]["payout"]["status"] == "envoye"
    (payout,) = await payouts_of(db_session, engagement)
    assert payout.amount_fcfa == NET
    assert str(engagement.intervention.id) in [i["id"] for i in resolved.json()["items"]]


async def test_an_admin_refunding_a_dispute_refunds_the_client(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _open_dispute(http, engagement, engagement.client)
        response = await _resolve(http, engagement, admin, "rembourse")

    body = response.json()
    assert body["status"] == "annulee"
    assert body["cancellation"]["kind"] == "arbitrage"
    assert body["cancellation"]["by"] == "admin"
    assert body["payment"]["status"] == "rembourse"
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE
    assert await payouts_of(db_session, engagement) == []


async def test_only_an_admin_can_resolve_a_dispute(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _open_dispute(http, engagement, engagement.client)
        by_client = await _resolve(http, engagement, engagement.client, "rembourse")
        by_artisan = await _resolve(http, engagement, engagement.artisan_user, "libere")

    assert by_client.status_code == 403
    assert by_artisan.status_code == 403
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.RETENU


async def test_resolving_without_a_dispute_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)

    async with client() as http:
        response = await _resolve(http, engagement, admin, "libere")

    assert response.status_code == 409


# ------------------------------------------------------------------ checkout sandbox


def _deliver_in_app() -> WebhookDeliverer:
    """Le « fournisseur » sandbox livre ses notifications à l'application
    elle-même (ASGI), comme il le ferait par HTTP."""

    async def deliver(url: str, body: bytes, headers: dict[str, str]) -> int:
        async with client() as http:
            return (
                await http.post("/api/v1/webhooks/payments", content=body, headers=headers)
            ).status_code

    return deliver


async def test_the_hosted_sandbox_checkout_pays_through_the_signed_webhook(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)
    app.dependency_overrides[get_webhook_deliverer] = _deliver_in_app

    async with client() as http:
        checkout_url = (await init_payment(http, engagement, "wave")).json()["checkout_url"]
        path = "/" + checkout_url.split("/", 3)[3]
        page = await http.get(path)
        submitted = await http.post(path, data={"outcome": "paye", "replay": "1"})

    assert page.status_code == 200
    assert "12 000 FCFA" in page.text
    assert "SANDBOX" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert submitted.status_code == 303
    assert submitted.headers["location"].endswith(
        f"/paiement/{engagement.intervention.id}?retour=succes"
    )
    # Livrée deux fois (rejeu demandé) : traitée une seule fois.
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.RETENU


async def test_the_sandbox_checkout_can_simulate_a_failure(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    app.dependency_overrides[get_webhook_deliverer] = _deliver_in_app

    async with client() as http:
        checkout_url = (await init_payment(http, engagement, "wave")).json()["checkout_url"]
        path = "/" + checkout_url.split("/", 3)[3]
        submitted = await http.post(path, data={"outcome": "echoue"})

    assert submitted.headers["location"].endswith("?retour=echec")
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.ECHOUE


async def test_a_tampered_sandbox_checkout_page_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        checkout_url = (await init_payment(http, engagement, "wave")).json()["checkout_url"]
        path = "/" + checkout_url.split("/", 3)[3]
        response = await http.get(path[:-4] + "AAAA")

    assert response.status_code == 400


async def test_expiry_of_an_unpaid_checkout_frees_the_completion(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        payment = await only_payment(db_session, engagement)
        payment.checkout_expires_at = datetime.now(UTC)
        await db_session.flush()
        response = await _complete(http, engagement)

    assert response.status_code == 200
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.ECHOUE
