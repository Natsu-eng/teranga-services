"""Fournisseur sandbox : il doit reproduire le contrat d'un agrégateur réel,
y compris ses garde-fous (signature, horodatage, jeton de checkout)."""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.models.enums import PaymentChannel, PayoutChannel
from app.services.payment_providers import build_payment_provider, resolve_webhook_secret
from app.services.payment_providers.base import (
    CheckoutRequest,
    InvalidWebhookSignatureError,
    MalformedWebhookError,
    PayoutRequest,
    RefundRequest,
)
from app.services.payment_providers.sandbox import (
    CHECKOUT_PATH,
    EVENT_COMPLETED,
    EVENT_FAILED,
    SIGNATURE_HEADER,
    SandboxProvider,
    sign_payload,
)

SECRET = "s" * 40
TOLERANCE = 300


def _provider(secret: str = SECRET) -> SandboxProvider:
    return SandboxProvider(
        webhook_secret=secret,
        checkout_base_url="http://backend.test/",
        tolerance_seconds=TOLERANCE,
    )


def _checkout_request(*, expires_in: timedelta = timedelta(minutes=30)) -> CheckoutRequest:
    return CheckoutRequest(
        payment_id="pay-1",
        amount_fcfa=12_000,
        currency="XOF",
        channel=PaymentChannel.WAVE,
        description="Plomberie",
        success_url="http://front.test/paiement/i1?retour=succes",
        error_url="http://front.test/paiement/i1?retour=echec",
        expires_at=datetime.now(UTC) + expires_in,
    )


def _event(
    *, event_type: str = EVENT_COMPLETED, amount: object = "12000", event_id: str = "EV_1"
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": event_type,
            "data": {"id": "sbx_cs_1", "amount": amount, "currency": "XOF"},
        }
    ).encode()


# ------------------------------------------------------------ checkout hébergé


async def test_checkout_is_hosted_outside_the_front_with_a_signed_token() -> None:
    provider = _provider()

    session = await provider.create_checkout(_checkout_request())

    assert session.checkout_url.startswith(f"http://backend.test{CHECKOUT_PATH}/")
    token = session.checkout_url.rsplit("/", 1)[1]
    claims = provider.read_checkout_token(token)
    assert claims["ref"] == session.provider_ref
    assert claims["amt"] == 12_000
    assert claims["pid"] == "pay-1"


async def test_the_same_payment_always_gets_the_same_reference() -> None:
    first = await _provider().create_checkout(_checkout_request())
    second = await _provider().create_checkout(_checkout_request())

    assert first.provider_ref == second.provider_ref


async def test_a_tampered_checkout_token_is_refused() -> None:
    provider = _provider()
    session = await provider.create_checkout(_checkout_request())
    token = session.checkout_url.rsplit("/", 1)[1]
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload[:-2]}AA.{signature}"

    with pytest.raises(InvalidWebhookSignatureError):
        provider.read_checkout_token(forged)


async def test_an_expired_checkout_page_is_refused() -> None:
    provider = _provider()
    session = await provider.create_checkout(_checkout_request(expires_in=timedelta(seconds=-5)))

    with pytest.raises(InvalidWebhookSignatureError):
        provider.read_checkout_token(session.checkout_url.rsplit("/", 1)[1])


async def test_a_checkout_token_from_another_secret_is_refused() -> None:
    session = await _provider("autre-secret-" * 4).create_checkout(_checkout_request())

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().read_checkout_token(session.checkout_url.rsplit("/", 1)[1])


# ------------------------------------------------------------ signature des webhooks


def test_a_correctly_signed_notification_is_accepted() -> None:
    payload = _event()

    _provider().verify_webhook_signature(payload, {SIGNATURE_HEADER: sign_payload(SECRET, payload)})


def test_the_header_name_is_case_insensitive() -> None:
    payload = _event()

    _provider().verify_webhook_signature(
        payload, {SIGNATURE_HEADER.lower(): sign_payload(SECRET, payload)}
    )


def test_one_valid_signature_among_several_is_enough_for_secret_rotation() -> None:
    payload = _event()
    signed_at = int(time.time())
    valid = sign_payload(SECRET, payload, timestamp=signed_at).split("v1=")[1]
    header = f"t={signed_at},v1={'0' * 64},v1={valid}"

    _provider().verify_webhook_signature(payload, {SIGNATURE_HEADER: header})


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {SIGNATURE_HEADER: ""},
        {SIGNATURE_HEADER: "n'importe quoi"},
        {SIGNATURE_HEADER: "t=abc,v1=00"},
        {SIGNATURE_HEADER: f"t={int(time.time())}"},
    ],
)
def test_a_missing_or_malformed_signature_is_refused(headers: dict[str, str]) -> None:
    with pytest.raises(InvalidWebhookSignatureError):
        _provider().verify_webhook_signature(_event(), headers)


def test_a_signature_made_with_another_secret_is_refused() -> None:
    payload = _event()

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().verify_webhook_signature(
            payload, {SIGNATURE_HEADER: sign_payload("x" * 40, payload)}
        )


def test_a_modified_body_is_refused() -> None:
    signature = sign_payload(SECRET, _event(amount="12000"))

    # Même signature, montant réécrit : refusé.
    with pytest.raises(InvalidWebhookSignatureError):
        _provider().verify_webhook_signature(_event(amount="1"), {SIGNATURE_HEADER: signature})


@pytest.mark.parametrize("offset", [-(TOLERANCE + 60), TOLERANCE + 60])
def test_a_signature_outside_the_time_window_is_refused(offset: int) -> None:
    payload = _event()
    header = sign_payload(SECRET, payload, timestamp=int(time.time()) + offset)

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().verify_webhook_signature(payload, {SIGNATURE_HEADER: header})


# ------------------------------------------------------------ lecture des événements


def test_a_completed_checkout_is_normalised() -> None:
    event = _provider().parse_event(_event())

    assert event.kind == "checkout_reussi"
    assert event.event_id == "EV_1"
    assert event.checkout_ref == "sbx_cs_1"
    assert event.amount_fcfa == 12_000
    assert event.currency == "XOF"


def test_a_failed_checkout_is_normalised() -> None:
    assert _provider().parse_event(_event(event_type=EVENT_FAILED)).kind == "checkout_echoue"


def test_an_unknown_event_type_is_reported_as_other() -> None:
    event = _provider().parse_event(_event(event_type="merchant.updated"))

    assert event.kind == "autre"
    assert event.raw_type == "merchant.updated"


@pytest.mark.parametrize(
    "payload",
    [
        b"pas du json",
        b"[]",
        b'{"type": "checkout.session.completed"}',
        b'{"id": "", "type": "checkout.session.completed"}',
        _event(amount="12000.50"),
        _event(amount="-12000"),
        _event(amount=12000.0),
        _event(amount="12 000"),
    ],
)
def test_an_unreadable_event_is_refused(payload: bytes) -> None:
    with pytest.raises(MalformedWebhookError):
        _provider().parse_event(payload)


# ------------------------------------------------------------ opérations idempotentes


async def test_refund_and_payout_references_are_idempotent() -> None:
    provider = _provider()
    refund = RefundRequest(
        provider_ref="sbx_cs_1", amount_fcfa=12_000, currency="XOF", idempotency_key="refund-1"
    )
    payout = PayoutRequest(
        amount_fcfa=10_800,
        currency="XOF",
        channel=PayoutChannel.WAVE,
        destination_phone="+221770000001",
        idempotency_key="payout-1",
        description="Versement",
    )

    assert (await provider.refund(refund)).reference == (await provider.refund(refund)).reference
    assert (await provider.send_payout(payout)).reference == (
        await provider.send_payout(payout)
    ).reference
    other = RefundRequest(
        provider_ref="sbx_cs_1", amount_fcfa=12_000, currency="XOF", idempotency_key="refund-2"
    )
    assert (await provider.refund(other)).reference != (await provider.refund(refund)).reference


# ------------------------------------------------------------ choix du fournisseur


def test_the_configured_provider_is_built_from_settings() -> None:
    settings = get_settings()

    provider = build_payment_provider(settings.model_copy(update={"payment_provider": "sandbox"}))
    disabled = build_payment_provider(settings.model_copy(update={"payment_provider": "disabled"}))

    assert provider is not None and provider.name == "sandbox"
    assert disabled is None


def test_the_dev_webhook_secret_is_derived_never_hard_coded() -> None:
    settings = get_settings().model_copy(update={"payment_webhook_secret": ""})
    other = settings.model_copy(update={"jwt_secret": "z" * 40})
    explicit = settings.model_copy(update={"payment_webhook_secret": "w" * 40})

    derived = resolve_webhook_secret(settings)

    assert len(derived) >= 32
    assert derived == resolve_webhook_secret(settings)
    assert derived != settings.jwt_secret
    assert derived != resolve_webhook_secret(other)
    assert resolve_webhook_secret(explicit) == "w" * 40
