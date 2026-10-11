"""Création + lecture de chaque modèle, et unicité du téléphone."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanTrade, Verification
from app.models.enums import (
    MessageKind,
    PaymentChannel,
    PaymentStatus,
    PayoutChannel,
    PayoutStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
    QuoteStatus,
    Role,
    VerificationDocType,
    VerificationStatus,
)
from app.models.intervention import Quote
from app.models.messaging import Conversation, Message
from app.models.otp import OtpCode
from app.models.payment import Payment, Payout, PlatformFee
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_commission_rate,
    make_intervention,
    make_service_request,
    make_trade,
    make_user,
    unique_phone,
)


async def test_full_graph_create_and_read(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session, code="plomberie")
    client = await make_user(db_session, role=Role.CLIENT, full_name="Awa Client")
    artisan_profile = await make_artisan_profile(db_session)
    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    service_request = await make_service_request(db_session, client=client, trade=trade)
    intervention = await make_intervention(
        db_session,
        service_request=service_request,
        client=client,
        artisan=artisan_profile,
        commission_rate=commission_rate,
    )

    artisan_trade = ArtisanTrade(
        artisan_id=artisan_profile.id,
        trade_id=trade.id,
        hourly_rate_fcfa=15_000,
        service_radius_m=5_000,
    )
    verification = Verification(
        artisan_id=artisan_profile.id,
        doc_type=VerificationDocType.CNI,
        doc_url="https://example.invalid/cni.jpg",
        status=VerificationStatus.APPROVED,
        reviewed_at=datetime.now(UTC),
    )
    quote = Quote(
        intervention_id=intervention.id,
        labor_fcfa=8_000,
        materials_fcfa=4_000,
        total_fcfa=12_000,
        status=QuoteStatus.ACCEPTE,
    )
    payment = Payment(
        intervention_id=intervention.id,
        amount_fcfa=12_000,
        channel=PaymentChannel.WAVE,
        status=PaymentStatus.LIBERE,
        provider="sandbox",
        provider_ref=f"sbx_cs_{intervention.id}",
    )
    platform_fee = PlatformFee(
        intervention_id=intervention.id,
        kind=PlatformFeeKind.COMMISSION,
        amount_fcfa=1_200,
        commission_rate_id=commission_rate.id,
        status=PlatformFeeStatus.COLLECTEE,
    )
    payout = Payout(
        artisan_id=artisan_profile.id,
        intervention_id=intervention.id,
        amount_fcfa=10_800,
        channel=PayoutChannel.WAVE,
        status=PayoutStatus.ENVOYE,
        destination_phone="+221770000001",
        provider="sandbox",
    )
    review = Review(
        intervention_id=intervention.id,
        author_id=client.id,
        artisan_id=artisan_profile.id,
        rating=5,
        comment="Impeccable.",
        contact_verified=True,
    )
    conversation = Conversation(
        service_request_id=service_request.id,
        intervention_id=intervention.id,
        client_id=client.id,
        artisan_id=artisan_profile.user_id,
    )
    db_session.add_all(
        [artisan_trade, verification, quote, payment, platform_fee, payout, review, conversation]
    )
    await db_session.flush()

    message = Message(
        conversation_id=conversation.id, sender_id=client.id, body="Bonjour", kind=MessageKind.TEXTE
    )
    otp = OtpCode(phone=client.phone, code_hash="hashed", expires_at=datetime.now(UTC))
    db_session.add_all([message, otp])
    await db_session.flush()

    # Relit chaque ligne depuis la base pour confirmer la persistance réelle.
    read_trade = (await db_session.execute(select(Trade).where(Trade.id == trade.id))).scalar_one()
    read_user = (await db_session.execute(select(User).where(User.id == client.id))).scalar_one()
    read_artisan_trade = (
        await db_session.execute(select(ArtisanTrade).where(ArtisanTrade.id == artisan_trade.id))
    ).scalar_one()
    read_verification = (
        await db_session.execute(select(Verification).where(Verification.id == verification.id))
    ).scalar_one()
    read_quote = (await db_session.execute(select(Quote).where(Quote.id == quote.id))).scalar_one()
    read_payment = (
        await db_session.execute(select(Payment).where(Payment.id == payment.id))
    ).scalar_one()
    read_platform_fee = (
        await db_session.execute(select(PlatformFee).where(PlatformFee.id == platform_fee.id))
    ).scalar_one()
    read_payout = (
        await db_session.execute(select(Payout).where(Payout.id == payout.id))
    ).scalar_one()
    read_review = (
        await db_session.execute(select(Review).where(Review.id == review.id))
    ).scalar_one()
    read_conversation = (
        await db_session.execute(select(Conversation).where(Conversation.id == conversation.id))
    ).scalar_one()
    read_message = (
        await db_session.execute(select(Message).where(Message.id == message.id))
    ).scalar_one()
    read_otp = (await db_session.execute(select(OtpCode).where(OtpCode.id == otp.id))).scalar_one()

    assert read_trade.code == trade.code
    assert read_user.full_name == "Awa Client"
    assert read_artisan_trade.hourly_rate_fcfa == 15_000
    assert read_verification.status == VerificationStatus.APPROVED
    assert read_quote.total_fcfa == 12_000
    assert read_payment.status == PaymentStatus.LIBERE
    assert read_platform_fee.amount_fcfa == 1_200
    assert read_payout.status == PayoutStatus.ENVOYE
    assert read_review.rating == 5
    assert read_conversation.client_id == client.id
    assert read_message.body == "Bonjour"
    assert read_otp.phone == client.phone


async def test_user_phone_is_unique(db_session: AsyncSession) -> None:
    phone = unique_phone()
    db_session.add(User(phone=phone, full_name="Premier", role=Role.CLIENT))
    await db_session.flush()

    db_session.add(User(phone=phone, full_name="Second", role=Role.CLIENT))
    with pytest.raises(IntegrityError):
        await db_session.flush()
