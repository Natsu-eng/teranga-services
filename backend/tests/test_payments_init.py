"""Initiation d'un paiement : `POST /api/v1/payments/init` (BUILD_PLAN.md §3.5)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider
from app.main import app
from app.models.commission import CommissionRate
from app.models.enums import (
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PlatformFeeStatus,
    QuoteStatus,
    Role,
)
from app.services.payment_providers.base import (
    CheckoutRequest,
    CheckoutSession,
    PaymentProviderError,
)
from app.services.payment_providers.sandbox import CHECKOUT_PATH
from tests.factories import make_commission_rate, make_engagement, make_quote, make_user
from tests.payments_helpers import (
    AMOUNT,
    COMMISSION,
    NET,
    auth,
    client,
    commission_of,
    event_body,
    init_payment,
    make_payable_engagement,
    only_payment,
    override_dependencies,
    payments_of,
    post_webhook,
    update_settings,
)


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession) -> Iterator[None]:
    with override_dependencies(db_session):
        yield


# ------------------------------------------------------------------ en ligne


async def test_online_payment_opens_a_hosted_checkout(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await init_payment(http, engagement, "wave")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "en_attente"
    assert body["channel"] == "wave"
    assert body["amount_fcfa"] == AMOUNT
    assert body["commission"] == {"rate_bps": 1000, "amount_fcfa": COMMISSION, "status": "due"}
    assert body["net_fcfa"] == NET
    assert CHECKOUT_PATH in body["checkout_url"]
    payment = await only_payment(db_session, engagement)
    assert payment.provider == "sandbox"
    assert payment.provider_ref is not None
    assert payment.amount_fcfa == AMOUNT


async def test_the_amount_always_comes_from_the_accepted_quote(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await http.post(
            "/api/v1/payments/init",
            # Tentative de fixer soi-même le montant : ignorée.
            json={
                "intervention_id": str(engagement.intervention.id),
                "channel": "wave",
                "amount_fcfa": 1,
                "amount": 1,
            },
            headers=auth(engagement.client),
        )

    assert response.status_code == 200, response.text
    assert response.json()["amount_fcfa"] == AMOUNT
    assert (await only_payment(db_session, engagement)).amount_fcfa == AMOUNT


async def test_commission_uses_the_rate_frozen_on_the_intervention(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)
    # Le taux du métier change APRÈS la création de l'intervention.
    frozen = await db_session.get(CommissionRate, engagement.intervention.commission_rate_id)
    assert frozen is not None and frozen.trade_id is not None
    frozen.effective_to = datetime.now(UTC)
    await db_session.flush()
    await make_commission_rate(db_session, rate_bps=2_500, trade_id=frozen.trade_id)

    async with client() as http:
        response = await init_payment(http, engagement, "wave")

    assert response.json()["commission"]["amount_fcfa"] == COMMISSION  # 10 %, pas 25 %
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.commission_rate_id == frozen.id


async def test_a_double_click_reuses_the_open_checkout(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        first = await init_payment(http, engagement, "wave")
        second = await init_payment(http, engagement, "wave")

    assert first.json()["checkout_url"] == second.json()["checkout_url"]
    assert len(await payments_of(db_session, engagement)) == 1


async def test_choosing_another_means_abandons_the_open_checkout(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        response = await init_payment(http, engagement, "orange_money")

    assert response.json()["channel"] == "orange_money"
    first, second = await payments_of(db_session, engagement)
    assert first.status is PaymentStatus.ANNULE
    assert second.status is PaymentStatus.EN_ATTENTE
    assert first.provider_ref != second.provider_ref


async def test_an_expired_checkout_is_replaced(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        await init_payment(http, engagement, "wave")
        expired = await only_payment(db_session, engagement)
        expired.checkout_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        response = await init_payment(http, engagement, "wave")

    assert response.status_code == 200
    first, second = await payments_of(db_session, engagement)
    assert first.status is PaymentStatus.ECHOUE
    assert second.status is PaymentStatus.EN_ATTENTE


async def test_paying_again_once_funds_are_held_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        await post_webhook(http, event_body(await only_payment(db_session, engagement)))
        again = await init_payment(http, engagement, "carte")

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PAIEMENT_DEJA_EFFECTUE"


# ------------------------------------------------------------------ espèces


async def test_cash_is_recorded_without_checkout_and_commission_is_due(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await init_payment(http, engagement, "cash")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "reussi"
    assert body["channel"] == "cash"
    assert body["checkout_url"] is None
    payment = await only_payment(db_session, engagement)
    assert payment.provider is None
    assert payment.paid_at is not None
    fee = await commission_of(db_session, engagement)
    assert fee is not None
    assert fee.status is PlatformFeeStatus.DUE
    assert fee.amount_fcfa == COMMISSION


async def test_cash_cannot_be_declared_twice(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "cash")
        again = await init_payment(http, engagement, "cash")

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PAIEMENT_DEJA_EFFECTUE"


async def test_declared_cash_can_still_be_replaced_by_an_online_payment(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "cash")
        response = await init_payment(http, engagement, "wave")

    assert response.json()["status"] == "en_attente"
    cash, online = await payments_of(db_session, engagement)
    assert cash.channel is PaymentChannel.CASH and cash.status is PaymentStatus.ANNULE
    assert online.status is PaymentStatus.EN_ATTENTE
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.DUE  # une seule commission


# ------------------------------------------------------------------ refus


async def test_only_the_client_of_the_intervention_can_pay(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)

    async with client() as http:
        artisan = await http.post(
            "/api/v1/payments/init",
            json={"intervention_id": str(engagement.intervention.id), "channel": "wave"},
            headers=auth(engagement.artisan_user),
        )
        third_party = await http.post(
            "/api/v1/payments/init",
            json={"intervention_id": str(engagement.intervention.id), "channel": "wave"},
            headers=auth(outsider),
        )
        missing = await http.post(
            "/api/v1/payments/init",
            json={"intervention_id": "00000000-0000-4000-8000-000000000000", "channel": "wave"},
            headers=auth(outsider),
        )

    assert artisan.status_code == 403
    assert third_party.status_code == 403
    assert third_party.json()["error"]["code"] == "INTERVENTION_ACCES_INTERDIT"
    assert missing.status_code == 404
    assert await payments_of(db_session, engagement) == []


@pytest.mark.parametrize(
    "status", [InterventionStatus.ACCEPTEE, InterventionStatus.TERMINEE, InterventionStatus.ANNULEE]
)
async def test_payment_is_refused_outside_the_work_in_progress_stage(
    db_session: AsyncSession, status: InterventionStatus
) -> None:
    engagement = await make_engagement(db_session, status=status)
    await make_quote(db_session, intervention=engagement.intervention, status=QuoteStatus.ACCEPTE)
    engagement.intervention.agreed_amount_fcfa = AMOUNT
    await db_session.flush()

    async with client() as http:
        response = await init_payment(http, engagement, "wave")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAIEMENT_NON_EXIGIBLE"


async def test_payment_is_refused_without_an_accepted_quote(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.EN_COURS)

    async with client() as http:
        response = await init_payment(http, engagement, "wave")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAIEMENT_NON_EXIGIBLE"


async def test_a_means_that_is_not_offered_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await init_payment(http, engagement, "free_money")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MOYEN_DE_PAIEMENT_INDISPONIBLE"


async def test_with_online_payment_disabled_only_cash_remains(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    update_settings(payment_provider="disabled")

    async with client() as http:
        options = await http.get("/api/v1/payments/options", headers=auth(engagement.client))
        online = await init_payment(http, engagement, "wave")
        cash = await init_payment(http, engagement, "cash")

    assert options.json() == {"online_channels": [], "cash_enabled": True, "currency": "XOF"}
    # Paiement en ligne refusé avec un message qui dit quoi faire.
    assert online.status_code == 422
    assert online.json()["error"]["code"] == "PAIEMENT_EN_LIGNE_INDISPONIBLE"
    assert "espèces" in online.json()["error"]["message"]
    # Les espèces fonctionnent, et le résumé dit qu'aucun séquestre n'est proposé.
    assert cash.status_code == 200
    assert cash.json()["status"] == "reussi"
    assert cash.json()["online_available"] is False


async def test_the_summary_says_when_online_payment_is_offered(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        view = await http.get(
            f"/api/v1/interventions/{engagement.intervention.id}", headers=auth(engagement.client)
        )

    assert view.json()["payment"]["online_available"] is True


async def test_options_list_the_configured_means(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        options = await http.get("/api/v1/payments/options", headers=auth(engagement.client))

    assert options.json() == {
        "online_channels": ["wave", "orange_money", "carte"],
        "cash_enabled": True,
        "currency": "XOF",
    }


class _FailingCheckout:
    """Fournisseur en panne à l'ouverture du checkout."""

    name = "sandbox"

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        raise PaymentProviderError("service indisponible")


async def test_a_provider_outage_leaves_nothing_behind(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    app.dependency_overrides[get_payment_provider] = lambda: _FailingCheckout()

    async with client() as http:
        response = await init_payment(http, engagement, "wave")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "FOURNISSEUR_PAIEMENT_INDISPONIBLE"
    await db_session.rollback()
    assert await payments_of(db_session, engagement) == []


async def test_payment_attempts_are_rate_limited(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    update_settings(rate_limit_payment_init_per_user_max=2)

    async with client() as http:
        statuses = [(await init_payment(http, engagement, "wave")).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
