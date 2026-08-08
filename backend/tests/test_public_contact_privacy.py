"""Verrou anti-fuite de contact (BUILD_PLAN.md, fix confidentialité du
contact) -- LE test critique de ce lot. Un compte créé avant le correctif
peut encore avoir `full_name` égal à son numéro de téléphone (ancien
placeholder, `app.services.auth`) : ce test garantit structurellement que
ce numéro n'apparaît JAMAIS dans une réponse publique, quel que soit le
champ, en cherchant la CHAÎNE EXACTE du numéro dans le corps brut de la
réponse -- pas seulement dans `full_name`, pour ne rater aucun chemin de
fuite (présent ou futur).
"""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.enums import (
    InterventionStatus,
    QuoteStatus,
    ReviewStatus,
    Role,
    ServiceRequestStatus,
    Urgency,
    VerificationDocType,
    VerificationStatus,
)
from app.models.artisan import ArtisanProfile
from app.models.intervention import Intervention, Quote
from app.models.request import ServiceRequest
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_trade,
    make_user,
    make_verification,
    point,
)

REFERENCE_LAT = 14.6937
REFERENCE_LNG = -17.4441


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _legacy_verified_artisan_with_phone_as_name(
    db_session: AsyncSession, *, trade: Trade
) -> tuple[User, ArtisanProfile]:
    """Reproduit exactement le bug constaté en prod avant ce correctif : un
    compte dont `full_name` vaut encore son numéro de téléphone (créé avant
    que le signup exige un nom -- impossible désormais via l'application,
    d'où la construction directe ici)."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan_user.full_name = artisan_user.phone  # simule le placeholder legacy
    await db_session.flush()
    artisan = await make_artisan_profile(
        db_session, user=artisan_user, lat=REFERENCE_LAT, lng=REFERENCE_LNG
    )
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.APPROVED,
    )
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.SELFIE,
        status=VerificationStatus.APPROVED,
    )
    return artisan_user, artisan


async def test_search_never_exposes_a_phone_number_even_for_a_legacy_placeholder_account(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    artisan_user, artisan = await _legacy_verified_artisan_with_phone_as_name(
        db_session, trade=trade
    )

    async with await _client() as client:
        response = await client.get(
            "/api/v1/artisans",
            params={"near": f"{REFERENCE_LAT},{REFERENCE_LNG}", "radius_m": 10_000},
        )

    assert response.status_code == 200
    assert str(artisan.id) in response.text  # sanity : l'artisan est bien dans cette réponse
    assert artisan_user.phone not in response.text
    item = next(i for i in response.json()["items"] if i["id"] == str(artisan.id))
    assert item["full_name"] != artisan_user.phone


async def test_detail_never_exposes_a_phone_number_even_for_a_legacy_placeholder_account(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    artisan_user, artisan = await _legacy_verified_artisan_with_phone_as_name(
        db_session, trade=trade
    )

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 200
    assert artisan_user.phone not in response.text
    assert response.json()["full_name"] != artisan_user.phone


async def test_reviews_list_never_exposes_a_phone_number_for_a_legacy_author(
    db_session: AsyncSession,
) -> None:
    """Même bug, chemin différent (`GET /artisans/{id}/reviews`, auteur =
    le client qui a laissé l'avis) -- corrigé par le même filet
    (`app.services.identity.public_display_name`)."""
    trade = await make_trade(db_session)
    artisan_user, artisan = await _legacy_verified_artisan_with_phone_as_name(
        db_session, trade=trade
    )

    author = await make_user(db_session, role=Role.CLIENT)
    author.full_name = author.phone  # même placeholder legacy, côté client cette fois
    await db_session.flush()

    service_request = ServiceRequest(
        client_id=author.id,
        trade_id=trade.id,
        description="Fuite d'eau.",
        location=point(REFERENCE_LAT, REFERENCE_LNG),
        urgency=Urgency.NORMAL,
        status=ServiceRequestStatus.CONVERTIE,
    )
    db_session.add(service_request)
    await db_session.flush()

    commission_rate = await make_commission_rate(db_session, trade_id=trade.id)
    intervention = Intervention(
        service_request_id=service_request.id,
        client_id=author.id,
        artisan_id=artisan.id,
        status=InterventionStatus.TERMINEE,
        commission_rate_id=commission_rate.id,
        completed_at=datetime.now(UTC),
    )
    db_session.add(intervention)
    await db_session.flush()

    db_session.add(
        Quote(
            intervention_id=intervention.id,
            labor_fcfa=8_000,
            materials_fcfa=4_000,
            total_fcfa=12_000,
            status=QuoteStatus.ACCEPTE,
        )
    )
    db_session.add(
        Review(
            intervention_id=intervention.id,
            author_id=author.id,
            artisan_id=artisan.id,
            rating=5,
            comment="Excellent travail.",
            contact_verified=True,
            status=ReviewStatus.PUBLIE,
        )
    )
    await db_session.flush()

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}/reviews")

    assert response.status_code == 200
    assert author.phone not in response.text
    assert response.json()["items"][0]["author_name"] != author.phone


async def test_search_shows_the_real_name_for_a_normal_account(db_session: AsyncSession) -> None:
    """Garde-fou anti-régression inverse : le masquage ne doit se déclencher
    QUE pour un nom qui ressemble à un numéro -- un vrai nom reste affiché
    tel quel."""
    trade = await make_trade(db_session)
    artisan_user = await make_user(db_session, role=Role.ARTISAN, full_name="Idrissa Diop")
    artisan = await make_artisan_profile(
        db_session, user=artisan_user, lat=REFERENCE_LAT, lng=REFERENCE_LNG
    )
    await make_artisan_trade(db_session, artisan=artisan, trade=trade)
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.CNI,
        status=VerificationStatus.APPROVED,
    )
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.SELFIE,
        status=VerificationStatus.APPROVED,
    )

    async with await _client() as client:
        response = await client.get(f"/api/v1/artisans/{artisan.id}")

    assert response.status_code == 200
    assert response.json()["full_name"] == "Idrissa Diop"
