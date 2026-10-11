"""Webhook des paiements : `POST /api/v1/webhooks/payments` (BUILD_PLAN.md §3.5).

Le fournisseur retente une même notification jusqu'à 24 h : elle ne doit
JAMAIS être traitée deux fois, et rien ne doit être accepté sans signature.
"""

import json
import time
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus, PayoutStatus
from app.models.payment import Payment
from app.services.payment_providers import resolve_webhook_secret
from app.services.payment_providers.sandbox import EVENT_FAILED, sign_payload
from tests.factories import Engagement
from tests.payments_helpers import (
    AMOUNT,
    NET,
    auth,
    client,
    count_events,
    current_settings,
    event_body,
    init_payment,
    make_payable_engagement,
    only_payment,
    override_dependencies,
    payments_of,
    payouts_of,
    post_webhook,
    update_settings,
)


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession) -> Iterator[None]:
    with override_dependencies(db_session):
        yield


async def _pending(
    http_client: AsyncClient, db_session: AsyncSession
) -> tuple[Engagement, Payment]:
    engagement = await make_payable_engagement(db_session)
    await init_payment(http_client, engagement, "wave")
    return engagement, await only_payment(db_session, engagement)


async def test_a_signed_success_puts_the_funds_in_escrow(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        response = await post_webhook(http, event_body(payment, event_id="EV_ok"))

    assert response.status_code == 200
    assert response.json() == {"status": "retenu"}
    payment = await only_payment(db_session, engagement)
    assert payment.status is PaymentStatus.RETENU
    assert payment.paid_at is not None
    assert await count_events(db_session, "EV_ok") == 1


@pytest.mark.parametrize(
    "signature",
    [
        "t=1,v1=" + "0" * 64,  # forgée
        sign_payload("un-autre-secret-de-quarante-caracteres!!", b"{}"),  # autre secret
        "",  # absente
    ],
)
async def test_an_unsigned_or_forged_notification_is_refused(
    db_session: AsyncSession, signature: str
) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        body = event_body(payment, event_id="EV_forge")
        response = await http.post(
            "/api/v1/webhooks/payments",
            content=body,
            headers={"Teranga-Sandbox-Signature": signature} if signature else {},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALIDE"
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.EN_ATTENTE
    assert await count_events(db_session, "EV_forge") == 0


async def test_a_signature_does_not_cover_another_body(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        genuine = event_body(payment, event_id="EV_x")
        signature = sign_payload(resolve_webhook_secret(current_settings()), genuine)
        tampered = genuine.replace(b'"12000"', b'"1"')
        response = await post_webhook(http, tampered, signature=signature)

    assert response.status_code == 401
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.EN_ATTENTE


async def test_an_old_signature_is_refused_even_if_valid(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        body = event_body(payment)
        old = sign_payload(
            resolve_webhook_secret(current_settings()), body, timestamp=int(time.time()) - 3_600
        )
        response = await post_webhook(http, body, signature=old)

    assert response.status_code == 401
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.EN_ATTENTE


async def test_a_replayed_notification_is_never_processed_twice(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        body = event_body(payment, event_id="EV_rejoue")
        first = await post_webhook(http, body)
        # Le fournisseur retente : même event id, nouvelle signature.
        replays = [await post_webhook(http, body) for _ in range(3)]

    assert first.json() == {"status": "retenu"}
    assert [r.status_code for r in replays] == [200, 200, 200]
    assert all(r.json() == {"status": "deja_traite"} for r in replays)
    assert await count_events(db_session, "EV_rejoue") == 1
    payments = await payments_of(db_session, engagement)
    assert len(payments) == 1
    assert payments[0].status is PaymentStatus.RETENU


async def test_a_replay_after_completion_never_pays_the_artisan_twice(
    db_session: AsyncSession,
) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        body = event_body(payment, event_id="EV_avant_fin")
        await post_webhook(http, body)
        completed = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/complete",
            headers=auth(engagement.client),
        )
        replay = await post_webhook(http, body)
        # Autre event id pour le même checkout (doublon côté fournisseur).
        duplicate = await post_webhook(http, event_body(payment, event_id="EV_doublon"))

    assert completed.status_code == 200, completed.text
    assert replay.json() == {"status": "deja_traite"}
    assert duplicate.json() == {"status": "deja_traite"}
    payouts = await payouts_of(db_session, engagement)
    assert len(payouts) == 1
    assert payouts[0].amount_fcfa == NET
    assert payouts[0].status is PayoutStatus.ENVOYE
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.LIBERE


async def test_a_notification_for_an_unknown_payment_is_ignored(db_session: AsyncSession) -> None:
    body = json.dumps(
        {
            "id": "EV_inconnu",
            "type": "checkout.session.completed",
            "data": {"id": "sbx_cs_qui_n_existe_pas", "amount": "12000", "currency": "XOF"},
        }
    ).encode()

    async with client() as http:
        response = await post_webhook(http, body)
        replay = await post_webhook(http, body)

    assert response.status_code == 200
    assert response.json() == {"status": "paiement_inconnu"}
    assert replay.json() == {"status": "deja_traite"}
    assert await count_events(db_session, "EV_inconnu") == 1


async def test_an_unknown_event_type_is_ignored(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        response = await post_webhook(
            http, event_body(payment, event_type="merchant.updated", event_id="EV_autre")
        )

    assert response.json() == {"status": "ignore"}
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.EN_ATTENTE


async def test_a_failed_checkout_is_recorded(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        response = await post_webhook(http, event_body(payment, event_type=EVENT_FAILED))

    assert response.json() == {"status": "echoue"}
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.ECHOUE


async def test_an_inconsistent_amount_never_puts_funds_in_escrow(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement, payment = await _pending(http, db_session)
        response = await post_webhook(http, event_body(payment, amount=AMOUNT - 1))

    assert response.json() == {"status": "montant_incoherent"}
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.EN_ATTENTE


async def test_a_late_payment_of_an_abandoned_checkout_is_refunded(
    db_session: AsyncSession,
) -> None:
    async with client() as http:
        engagement, abandoned = await _pending(http, db_session)
        # Le client choisit un autre moyen : la première page est abandonnée...
        await init_payment(http, engagement, "orange_money")
        # ... mais il l'avait payée quand même.
        response = await post_webhook(http, event_body(abandoned))

    assert response.json() == {"status": "rembourse_paiement_tardif"}
    first, second = await payments_of(db_session, engagement)
    assert first.status is PaymentStatus.REMBOURSE
    assert first.refund_ref is not None
    assert second.status is PaymentStatus.EN_ATTENTE


async def test_a_signed_but_unreadable_notification_is_rejected(db_session: AsyncSession) -> None:
    async with client() as http:
        response = await post_webhook(http, b'{"id": "EV_1", "type": 42}')

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEBHOOK_ILLISIBLE"


async def test_an_oversized_notification_is_refused_before_reading_it(
    db_session: AsyncSession,
) -> None:
    update_settings(payment_webhook_max_body_bytes=1_024)

    async with client() as http:
        response = await post_webhook(http, b"x" * 2_048)

    assert response.status_code == 413


async def test_the_webhook_does_not_exist_when_online_payment_is_disabled(
    db_session: AsyncSession,
) -> None:
    update_settings(payment_provider="disabled")

    async with client() as http:
        response = await post_webhook(http, b"{}", signature="t=1,v1=00")

    assert response.status_code == 404
