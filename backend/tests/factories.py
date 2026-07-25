"""Petites fabriques pour composer le graphe dont un test a besoin.

Ce ne sont pas des fixtures : chaque fonction est appelée explicitement,
avec les seuls paramètres qui comptent pour le test en cours. Aucun test
n'a besoin du graphe complet.
"""

import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artisan import ArtisanProfile, ArtisanTrade, Verification
from app.models.commission import CommissionRate
from app.models.enums import (
    ArtisanVerifiedStatus,
    InterventionStatus,
    Locale,
    PaymentChannel,
    PaymentStatus,
    QuoteStatus,
    ReviewStatus,
    Role,
    ServiceRequestStatus,
    SubscriptionTier,
    Urgency,
    VerificationDocType,
    VerificationStatus,
)
from app.models.intervention import Intervention, Quote
from app.models.payment import Payment
from app.models.request import ServiceRequest
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User

# Le Plateau, Dakar -- utilisé comme point par défaut quand la position
# géographique précise n'est pas ce que le test vérifie.
DEFAULT_LAT = 14.6937
DEFAULT_LNG = -17.4441


def unique_phone() -> str:
    # Préfixe "77" fixe (opérateur mobile réellement alloué au Sénégal) --
    # depuis le Lot 8, les numéros passent par une validation `phonenumbers`
    # réelle (app.core.phone), un préfixe choisi au hasard ne serait valide
    # qu'une partie du temps.
    return f"+22177{uuid.uuid4().int % 10**7:07d}"


def point(lat: float = DEFAULT_LAT, lng: float = DEFAULT_LNG) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def bounding_box_polygon(
    *, min_lat: float, max_lat: float, min_lng: float, max_lng: float
) -> WKTElement:
    corners = [
        (min_lng, min_lat),
        (max_lng, min_lat),
        (max_lng, max_lat),
        (min_lng, max_lat),
        (min_lng, min_lat),  # anneau fermé -- premier point == dernier point
    ]
    coords = ", ".join(f"{lng} {lat}" for lng, lat in corners)
    return WKTElement(f"POLYGON(({coords}))", srid=4326)


async def make_trade(session: AsyncSession, *, code: str = "plomberie") -> Trade:
    trade = Trade(code=f"{code}-{uuid.uuid4().hex[:8]}", label_fr=code.capitalize(), sort_order=1)
    session.add(trade)
    await session.flush()
    return trade


async def make_user(
    session: AsyncSession, *, role: Role = Role.CLIENT, full_name: str = "Test User"
) -> User:
    user = User(phone=unique_phone(), full_name=full_name, role=role, locale=Locale.FR)
    session.add(user)
    await session.flush()
    return user


async def make_artisan_profile(
    session: AsyncSession,
    *,
    user: User | None = None,
    lat: float = DEFAULT_LAT,
    lng: float = DEFAULT_LNG,
    bio: str | None = None,
    is_available: bool = True,
) -> ArtisanProfile:
    artisan_user = user or await make_user(session, role=Role.ARTISAN, full_name="Test Artisan")
    profile = ArtisanProfile(
        user_id=artisan_user.id,
        base_location=point(lat, lng),
        bio=bio,
        is_available=is_available,
        verified_status=ArtisanVerifiedStatus.VERIFIED,
        subscription_tier=SubscriptionTier.FREE,
    )
    session.add(profile)
    await session.flush()
    return profile


async def make_artisan_trade(
    session: AsyncSession,
    *,
    artisan: ArtisanProfile,
    trade: Trade,
    hourly_rate_fcfa: int = 15_000,
    service_radius_m: int = 5_000,
    service_area: WKTElement | None = None,
) -> ArtisanTrade:
    artisan_trade = ArtisanTrade(
        artisan_id=artisan.id,
        trade_id=trade.id,
        hourly_rate_fcfa=hourly_rate_fcfa,
        service_radius_m=service_radius_m,
        service_area=service_area,
    )
    session.add(artisan_trade)
    await session.flush()
    return artisan_trade


async def make_verification(
    session: AsyncSession,
    *,
    artisan: ArtisanProfile,
    doc_type: VerificationDocType = VerificationDocType.CNI,
    status: VerificationStatus = VerificationStatus.APPROVED,
    created_at: datetime | None = None,
) -> Verification:
    verification = Verification(
        artisan_id=artisan.id,
        doc_type=doc_type,
        doc_url="https://example.invalid/test/doc.jpg",
        status=status,
    )
    if created_at is not None:
        verification.created_at = created_at
    session.add(verification)
    await session.flush()
    return verification


async def make_commission_rate(
    session: AsyncSession, *, rate_bps: int = 1000, trade_id: uuid.UUID | None = None
) -> CommissionRate:
    # `trade_id` par défaut à None (portée "tous métiers") entrerait en
    # collision (contrainte d'exclusion) avec le taux par défaut semé par
    # scripts/seed.py, réellement présent en base de dev -- d'où le scoping
    # à un trade_id précis (celui du test appelant) par défaut des tests.
    rate = CommissionRate(rate_bps=rate_bps, trade_id=trade_id, effective_from=datetime.now(UTC))
    session.add(rate)
    await session.flush()
    return rate


async def make_service_request(
    session: AsyncSession,
    *,
    client: User,
    trade: Trade,
    lat: float = DEFAULT_LAT,
    lng: float = DEFAULT_LNG,
) -> ServiceRequest:
    request = ServiceRequest(
        client_id=client.id,
        trade_id=trade.id,
        description="Demande de test.",
        location=point(lat, lng),
        urgency=Urgency.NORMAL,
        status=ServiceRequestStatus.CONVERTIE,
    )
    session.add(request)
    await session.flush()
    return request


async def make_intervention(
    session: AsyncSession,
    *,
    service_request: ServiceRequest,
    client: User,
    artisan: ArtisanProfile,
    commission_rate: CommissionRate,
    status: InterventionStatus = InterventionStatus.TERMINEE,
) -> Intervention:
    intervention = Intervention(
        service_request_id=service_request.id,
        client_id=client.id,
        artisan_id=artisan.id,
        status=status,
        commission_rate_id=commission_rate.id,
        completed_at=datetime.now(UTC) if status == InterventionStatus.TERMINEE else None,
    )
    session.add(intervention)
    await session.flush()
    return intervention


async def make_quote(
    session: AsyncSession,
    *,
    intervention: Intervention,
    labor_fcfa: int = 8_000,
    materials_fcfa: int = 4_000,
    status: QuoteStatus = QuoteStatus.PROPOSE,
) -> Quote:
    quote = Quote(
        intervention_id=intervention.id,
        labor_fcfa=labor_fcfa,
        materials_fcfa=materials_fcfa,
        total_fcfa=labor_fcfa + materials_fcfa,
        status=status,
    )
    session.add(quote)
    await session.flush()
    return quote


async def make_payment(
    session: AsyncSession,
    *,
    intervention: Intervention,
    amount_fcfa: int,
    status: PaymentStatus = PaymentStatus.REUSSI,
    channel: PaymentChannel = PaymentChannel.WAVE,
) -> Payment:
    payment = Payment(
        intervention_id=intervention.id, amount_fcfa=amount_fcfa, channel=channel, status=status
    )
    session.add(payment)
    await session.flush()
    return payment


async def make_review(
    session: AsyncSession,
    *,
    intervention: Intervention,
    author: User,
    artisan: ArtisanProfile,
    rating: int = 5,
    status: ReviewStatus = ReviewStatus.PUBLIE,
    comment: str = "Avis de test.",
) -> Review:
    # Le trigger DB `trg_review_requires_completed_intervention` exige que
    # `intervention` soit déjà TERMINEE -- voir make_intervention.
    review = Review(
        intervention_id=intervention.id,
        author_id=author.id,
        artisan_id=artisan.id,
        rating=rating,
        comment=comment,
        contact_verified=True,
        status=status,
    )
    session.add(review)
    await session.flush()
    return review
