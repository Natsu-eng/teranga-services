"""Jeu de données de développement, idempotent.

JAMAIS exécuté automatiquement au démarrage de l'application -- toujours à la
main :

    uv run python scripts/seed.py

Sème :
- les métiers de `trade` (plomberie, électricité, climatisation, menuiserie,
  maçonnerie) ;
- un `commission_rate` à 10 % (rate_bps=1000), tous métiers, tous paliers ;
- les 3 artisans du mock frontend (`frontend/src/data/mockData.ts`), en
  vraies lignes cohérentes (user + artisan_profile + artisan_trade +
  verification approuvée), avec des coordonnées réelles de quartiers de
  Dakar ;
- quelques avis liés à des interventions terminées, portés par des clients
  distincts (idem mock) ;
- l'utilisateur client correspondant à `CURRENT_USER` du mock frontend.

Idempotent par clé naturelle (téléphone, code métier) : relancer ce script
ne duplique rien. Un utilisateur (par téléphone) déjà présent signale que
tout son scénario associé (profil, avis...) a déjà été semé -- ce script ne
répare pas un état partiel, il saute simplement le scénario.

Note de conception : contrairement à `CURRENT_USER.artisanId` dans le mock
frontend (qui fait pointer le même utilisateur démo vers un profil
artisan), le client de démo et l'artisan Idrissa Diop sont ici deux
comptes distincts -- un `user` n'a qu'un seul `role`, contrôlé serveur
(BUILD_PLAN.md §1, §4).
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

# Exécuté comme un script de fichier (pas `python -m`) : Python met le
# dossier scripts/ sur sys.path, pas backend/. Sans ceci, `import app` échoue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.artisan import ArtisanProfile, ArtisanTrade, Verification
from app.models.commission import CommissionRate
from app.models.enums import (
    ArtisanVerifiedStatus,
    InterventionStatus,
    Locale,
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
from app.models.request import ServiceRequest
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User

TRADES = [
    ("plomberie", "Plomberie", 1),
    ("electricite", "Électricité", 2),
    ("climatisation", "Climatisation", 3),
    ("menuiserie", "Menuiserie", 4),
    ("maconnerie", "Maçonnerie", 5),
]

DEFAULT_COMMISSION_RATE_BPS = 1000

CLIENT_PHONE = "+221771234501"
CLIENT_NAME = "Diandé Diallo"


class ArtisanSeed(TypedDict):
    phone: str
    full_name: str
    trade_code: str
    bio: str
    years_experience: int
    hourly_rate_fcfa: int
    lat: float
    lng: float


class ReviewSeed(TypedDict):
    author_phone: str
    author_name: str
    artisan_phone: str
    rating: int
    comment: str
    labor_fcfa: int
    materials_fcfa: int


# Coordonnées réelles de quartiers de Dakar (lat, lng).
ARTISANS: list[ArtisanSeed] = [
    {
        "phone": "+221771234502",
        "full_name": "Idrissa Diop",
        "trade_code": "plomberie",
        "bio": (
            "Artisan passionné avec plus de 8 ans d'expérience dans la plomberie "
            "sanitaire et le dépannage d'urgence à Dakar. Travail soigné et garanti. "
            "Spécialisé dans les installations résidentielles haut de gamme et la "
            "maintenance préventive."
        ),
        "years_experience": 8,
        "hourly_rate_fcfa": 15_000,
        "lat": 14.6937,
        "lng": -17.4441,  # Le Plateau, Dakar
    },
    {
        "phone": "+221771234503",
        "full_name": "Maty Ndiaye",
        "trade_code": "electricite",
        "bio": (
            "Électricienne diplômée avec 6 ans d'expérience. Installation complète, "
            "mise aux normes NFC 15-100 et dépannages d'urgence à Dakar."
        ),
        "years_experience": 6,
        "hourly_rate_fcfa": 20_000,
        "lat": 14.7256,
        "lng": -17.4914,  # Ouakam, Dakar
    },
    {
        "phone": "+221771234504",
        "full_name": "Ousmane Fall",
        "trade_code": "climatisation",
        "bio": (
            "Spécialiste de la climatisation résidentielle et tertiaire. Nettoyage "
            "antibactérien, recharge de gaz R410/R32 et installation Inverter."
        ),
        "years_experience": 10,
        "hourly_rate_fcfa": 18_000,
        "lat": 14.7444,
        "lng": -17.5133,  # Almadies, Dakar
    },
]

REVIEWS: list[ReviewSeed] = [
    {
        "author_phone": "+221771234505",
        "author_name": "Fatou K.",
        "artisan_phone": "+221771234502",  # Idrissa Diop
        "rating": 5,
        "comment": (
            "Excellent travail, très ponctuel ! Idrissa a su réparer une fuite "
            "complexe en moins d'une heure."
        ),
        "labor_fcfa": 8_000,
        "materials_fcfa": 4_000,
    },
    {
        "author_phone": "+221771234506",
        "author_name": "Moussa S.",
        "artisan_phone": "+221771234502",  # Idrissa Diop
        "rating": 5,
        "comment": (
            "Professionnel et honnête. Je recommande vivement pour tout ce qui "
            "touche à la plomberie sanitaire."
        ),
        "labor_fcfa": 10_000,
        "materials_fcfa": 5_000,
    },
    {
        "author_phone": "+221771234507",
        "author_name": "Awa D.",
        "artisan_phone": "+221771234503",  # Maty Ndiaye
        "rating": 5,
        "comment": "Maty a remis à neuf tout notre tableau électrique. Très soigneuse.",
        "labor_fcfa": 15_000,
        "materials_fcfa": 8_000,
    },
]


def _point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


async def _get_or_create_trade(
    session: AsyncSession, code: str, label_fr: str, sort_order: int
) -> Trade:
    trade = (await session.execute(select(Trade).where(Trade.code == code))).scalar_one_or_none()
    if trade is not None:
        return trade
    trade = Trade(code=code, label_fr=label_fr, sort_order=sort_order, is_active=True)
    session.add(trade)
    await session.flush()
    print(f"  + trade {code!r}")
    return trade


async def _seed_trades(session: AsyncSession) -> dict[str, Trade]:
    return {
        code: await _get_or_create_trade(session, code, label_fr, sort_order)
        for code, label_fr, sort_order in TRADES
    }


async def _seed_default_commission_rate(session: AsyncSession) -> CommissionRate:
    existing = (
        await session.execute(
            select(CommissionRate).where(
                CommissionRate.trade_id.is_(None),
                CommissionRate.tier.is_(None),
                CommissionRate.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    rate = CommissionRate(
        rate_bps=DEFAULT_COMMISSION_RATE_BPS,
        trade_id=None,
        tier=None,
        effective_from=datetime.now(UTC),
    )
    session.add(rate)
    await session.flush()
    print(
        f"  + commission_rate par défaut ({DEFAULT_COMMISSION_RATE_BPS} bps, tous métiers/paliers)"
    )
    return rate


async def _get_or_create_user(
    session: AsyncSession, *, phone: str, full_name: str, role: Role
) -> tuple[User, bool]:
    user = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if user is not None:
        return user, False
    user = User(
        phone=phone,
        full_name=full_name,
        role=role,
        locale=Locale.FR,
        phone_verified_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    print(f"  + user {full_name!r} ({role.value}, {phone})")
    return user, True


async def _seed_artisans(
    session: AsyncSession, trades: dict[str, Trade]
) -> dict[str, ArtisanProfile]:
    profiles: dict[str, ArtisanProfile] = {}
    for artisan in ARTISANS:
        user, created = await _get_or_create_user(
            session, phone=artisan["phone"], full_name=artisan["full_name"], role=Role.ARTISAN
        )
        if not created:
            profiles[artisan["phone"]] = (
                await session.execute(
                    select(ArtisanProfile).where(ArtisanProfile.user_id == user.id)
                )
            ).scalar_one()
            continue

        profile = ArtisanProfile(
            user_id=user.id,
            bio=artisan["bio"],
            years_experience=artisan["years_experience"],
            base_location=_point(artisan["lat"], artisan["lng"]),
            is_available=True,
            verified_status=ArtisanVerifiedStatus.VERIFIED,
            subscription_tier=SubscriptionTier.VERIFIED,
        )
        session.add(profile)
        await session.flush()

        session.add(
            ArtisanTrade(
                artisan_id=profile.id,
                trade_id=trades[artisan["trade_code"]].id,
                hourly_rate_fcfa=artisan["hourly_rate_fcfa"],
                service_radius_m=5_000,
            )
        )
        session.add(
            Verification(
                artisan_id=profile.id,
                doc_type=VerificationDocType.CNI,
                doc_url="https://example.invalid/dev-seed/cni-placeholder.jpg",
                status=VerificationStatus.APPROVED,
                reviewed_at=datetime.now(UTC),
            )
        )
        profiles[artisan["phone"]] = profile
    return profiles


async def _seed_reviews(
    session: AsyncSession, artisan_profiles: dict[str, ArtisanProfile], rate: CommissionRate
) -> None:
    artisans_by_phone = {a["phone"]: a for a in ARTISANS}

    for review_data in REVIEWS:
        author, created = await _get_or_create_user(
            session,
            phone=review_data["author_phone"],
            full_name=review_data["author_name"],
            role=Role.CLIENT,
        )
        if not created:
            continue  # scénario déjà semé lors d'un run précédent

        artisan_profile = artisan_profiles[review_data["artisan_phone"]]
        artisan_info = artisans_by_phone[review_data["artisan_phone"]]
        artisan_trade = (
            await session.execute(
                select(ArtisanTrade).where(ArtisanTrade.artisan_id == artisan_profile.id)
            )
        ).scalar_one()

        service_request = ServiceRequest(
            client_id=author.id,
            trade_id=artisan_trade.trade_id,
            description=(
                f"Intervention de {artisan_info['full_name']} -- jeu de données de développement."
            ),
            location=_point(artisan_info["lat"], artisan_info["lng"]),
            urgency=Urgency.NORMAL,
            status=ServiceRequestStatus.CONVERTIE,
        )
        session.add(service_request)
        await session.flush()

        total_fcfa = review_data["labor_fcfa"] + review_data["materials_fcfa"]
        intervention = Intervention(
            service_request_id=service_request.id,
            client_id=author.id,
            artisan_id=artisan_profile.id,
            status=InterventionStatus.TERMINEE,
            commission_rate_id=rate.id,
            agreed_amount_fcfa=total_fcfa,
            completed_at=datetime.now(UTC) - timedelta(days=3),
        )
        session.add(intervention)
        await session.flush()

        session.add(
            Quote(
                intervention_id=intervention.id,
                labor_fcfa=review_data["labor_fcfa"],
                materials_fcfa=review_data["materials_fcfa"],
                total_fcfa=total_fcfa,
                status=QuoteStatus.ACCEPTE,
            )
        )
        session.add(
            Review(
                intervention_id=intervention.id,
                author_id=author.id,
                artisan_id=artisan_profile.id,
                rating=review_data["rating"],
                comment=review_data["comment"],
                contact_verified=True,
                status=ReviewStatus.PUBLIE,
            )
        )
        print(f"  + review de {review_data['author_name']!r} sur {artisan_info['full_name']!r}")


async def seed(session: AsyncSession) -> None:
    print("Métiers :")
    trades = await _seed_trades(session)

    print("Taux de commission :")
    rate = await _seed_default_commission_rate(session)

    print("Client de démo :")
    await _get_or_create_user(session, phone=CLIENT_PHONE, full_name=CLIENT_NAME, role=Role.CLIENT)

    print("Artisans :")
    artisan_profiles = await _seed_artisans(session, trades)

    print("Avis :")
    await _seed_reviews(session, artisan_profiles, rate)


async def main() -> None:
    async with async_session_maker() as session, session.begin():
        await seed(session)
    print("Seed terminé.")


if __name__ == "__main__":
    asyncio.run(main())
