"""Localisation explicite de la demande et éligibilité avant envoi
(lot `fix/localisation-demande`).

- la demande enregistre le lieu CONFIRMÉ par le client (libellé + point) ;
- `GET /requests/me/eligibility` et `GET /artisans/{id}/coverage` disent,
  en lecture seule, si un artisan couvre une demande / un lieu ;
- leur verdict est toujours celui de `POST /interventions`, qui reste le
  dernier rempart (un envoi hors zone est refusé quoi qu'affiche l'écran).
"""

from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import Role, ServiceRequestStatus, VerificationDocType, VerificationStatus
from app.models.request import ServiceRequest
from app.models.trade import Trade
from app.models.user import User
from tests.factories import (
    make_artisan_profile,
    make_artisan_trade,
    make_commission_rate,
    make_service_request,
    make_trade,
    make_user,
    make_verification,
)

# Repères réels : l'artisan est basé au Plateau (Dakar) avec 10 km de rayon.
PLATEAU = (14.6681, -17.4339)
ALMADIES = (14.7419, -17.5080)  # ~11,5 km du Plateau : hors d'un rayon de 10 km
OUAKAM = (14.7225, -17.4878)  # ~8,4 km : dans le rayon
PARIS_NORD = (48.9097, 2.3819)  # la situation réellement observée en test manuel
RADIUS_M = 10_000


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Iterator[None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.pop(get_session, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _verified_artisan(
    db_session: AsyncSession, trade: Trade, *, verified: bool = True, with_rate: bool = True
) -> ArtisanProfile:
    artisan = await make_artisan_profile(db_session, lat=PLATEAU[0], lng=PLATEAU[1])
    await make_artisan_trade(db_session, artisan=artisan, trade=trade, service_radius_m=RADIUS_M)
    if verified:
        for doc_type in (VerificationDocType.CNI, VerificationDocType.SELFIE):
            await make_verification(
                db_session, artisan=artisan, doc_type=doc_type, status=VerificationStatus.APPROVED
            )
    if with_rate:
        # Un seul taux en vigueur par métier (contrainte d'exclusion).
        await make_commission_rate(db_session, trade_id=trade.id)
    return artisan


async def _open_request(
    db_session: AsyncSession, *, client: User, trade: Trade, at: tuple[float, float]
) -> ServiceRequest:
    request = await make_service_request(
        db_session, client=client, trade=trade, lat=at[0], lng=at[1]
    )
    request.status = ServiceRequestStatus.OUVERTE
    await db_session.flush()
    return request


# ------------------------------------------------------------------ lieu confirmé


async def test_the_request_stores_the_place_the_client_confirmed(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)

    async with _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json={
                "trade_code": trade.code,
                "description": "Fuite sous l'évier.",
                "location": {"lat": PLATEAU[0], "lng": PLATEAU[1]},
                "location_label": "  Dakar   Plateau ",
            },
            headers=_auth(client),
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["location"] == {"lat": pytest.approx(PLATEAU[0]), "lng": pytest.approx(PLATEAU[1])}
    assert body["location_label"] == "Dakar Plateau"
    stored = await db_session.get(ServiceRequest, body["id"])
    assert stored is not None and stored.location_label == "Dakar Plateau"


@pytest.mark.parametrize(("label", "expected"), [(None, None), ("   ", None)])
async def test_a_request_without_label_stays_valid(
    db_session: AsyncSession, label: str | None, expected: str | None
) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)

    async with _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json={
                "trade_code": trade.code,
                "description": "Fuite.",
                "location": {"lat": PLATEAU[0], "lng": PLATEAU[1]},
                "location_label": label,
            },
            headers=_auth(client),
        )

    assert response.status_code == 201
    assert response.json()["location_label"] == expected


async def test_an_overlong_place_label_is_refused(db_session: AsyncSession) -> None:
    trade = await make_trade(db_session)
    client = await make_user(db_session, role=Role.CLIENT)

    async with _client() as http:
        response = await http.post(
            "/api/v1/requests",
            json={
                "trade_code": trade.code,
                "description": "Fuite.",
                "location": {"lat": PLATEAU[0], "lng": PLATEAU[1]},
                "location_label": "x" * 121,
            },
            headers=_auth(client),
        )

    assert response.status_code == 422


# ------------------------------------------------------------------ éligibilité des demandes


async def test_each_open_request_is_marked_for_the_artisan(db_session: AsyncSession) -> None:
    plumbing = await make_trade(db_session, code="plomberie")
    painting = await make_trade(db_session, code="peinture")
    artisan = await _verified_artisan(db_session, plumbing)
    client = await make_user(db_session, role=Role.CLIENT)
    other_client = await make_user(db_session, role=Role.CLIENT)

    covered = await _open_request(db_session, client=client, trade=plumbing, at=OUAKAM)
    far = await _open_request(db_session, client=client, trade=plumbing, at=PARIS_NORD)
    just_outside = await _open_request(db_session, client=client, trade=plumbing, at=ALMADIES)
    other_trade = await _open_request(db_session, client=client, trade=painting, at=PLATEAU)
    # Ni une demande déjà en relation, ni la demande d'un autre client.
    closed = await make_service_request(db_session, client=client, trade=plumbing)
    foreign = await _open_request(db_session, client=other_client, trade=plumbing, at=PLATEAU)

    async with _client() as http:
        response = await http.get(
            "/api/v1/requests/me/eligibility",
            params={"artisan_id": str(artisan.id)},
            headers=_auth(client),
        )

    assert response.status_code == 200, response.text
    verdicts = {item["request_id"]: (item["eligible"], item["reason"]) for item in response.json()}
    assert verdicts == {
        str(covered.id): (True, None),
        str(far.id): (False, "hors_zone"),
        str(just_outside.id): (False, "hors_zone"),
        str(other_trade.id): (False, "metier_non_exerce"),
    }
    assert str(closed.id) not in verdicts
    assert str(foreign.id) not in verdicts


async def test_the_marking_always_matches_the_server_decision(db_session: AsyncSession) -> None:
    """Ce que l'écran annonce est exactement ce que `POST /interventions`
    décide — et un envoi hors zone reste refusé (dernier rempart)."""
    trade = await make_trade(db_session)
    artisan = await _verified_artisan(db_session, trade)
    client = await make_user(db_session, role=Role.CLIENT)
    requests = [
        await _open_request(db_session, client=client, trade=trade, at=at)
        for at in (OUAKAM, PARIS_NORD, ALMADIES)
    ]

    async with _client() as http:
        marks = (
            await http.get(
                "/api/v1/requests/me/eligibility",
                params={"artisan_id": str(artisan.id)},
                headers=_auth(client),
            )
        ).json()
        by_id = {item["request_id"]: item for item in marks}
        for request in requests:
            sent = await http.post(
                "/api/v1/interventions",
                json={"service_request_id": str(request.id), "artisan_id": str(artisan.id)},
                headers=_auth(client),
            )
            mark = by_id[str(request.id)]
            if mark["eligible"]:
                assert sent.status_code == 201, sent.text
            else:
                assert sent.status_code == 422
                assert sent.json()["error"]["code"] == "ARTISAN_HORS_ZONE"


async def test_eligibility_is_reserved_to_clients_and_known_artisans(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    artisan = await _verified_artisan(db_session, trade)
    client = await make_user(db_session, role=Role.CLIENT)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)

    async with _client() as http:
        anonymous = await http.get(
            "/api/v1/requests/me/eligibility", params={"artisan_id": str(artisan.id)}
        )
        as_artisan = await http.get(
            "/api/v1/requests/me/eligibility",
            params={"artisan_id": str(artisan.id)},
            headers=_auth(artisan_user),
        )
        unknown = await http.get(
            "/api/v1/requests/me/eligibility",
            params={"artisan_id": "00000000-0000-4000-8000-000000000000"},
            headers=_auth(client),
        )

    assert anonymous.status_code == 401
    assert as_artisan.status_code == 403
    assert unknown.status_code == 404


# ------------------------------------------------------------------ couverture d'un lieu


@pytest.mark.parametrize(
    ("at", "eligible", "reason"),
    [
        (PLATEAU, True, None),
        (OUAKAM, True, None),
        (ALMADIES, False, "hors_zone"),
        (PARIS_NORD, False, "hors_zone"),
    ],
)
async def test_coverage_of_a_place_before_any_request_exists(
    db_session: AsyncSession, at: tuple[float, float], eligible: bool, reason: str | None
) -> None:
    trade = await make_trade(db_session)
    artisan = await _verified_artisan(db_session, trade)

    async with _client() as http:
        # Public : un visiteur décrit son besoin avant de se connecter.
        response = await http.get(
            f"/api/v1/artisans/{artisan.id}/coverage",
            params={"trade": trade.code, "lat": at[0], "lng": at[1]},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"eligible": eligible, "reason": reason}


async def test_coverage_reports_an_unverified_artisan_or_another_trade(
    db_session: AsyncSession,
) -> None:
    trade = await make_trade(db_session)
    other_trade = await make_trade(db_session, code="peinture")
    unverified = await _verified_artisan(db_session, trade, verified=False)
    verified = await _verified_artisan(db_session, trade, with_rate=False)

    async with _client() as http:
        not_verified = await http.get(
            f"/api/v1/artisans/{unverified.id}/coverage",
            params={"trade": trade.code, "lat": PLATEAU[0], "lng": PLATEAU[1]},
        )
        wrong_trade = await http.get(
            f"/api/v1/artisans/{verified.id}/coverage",
            params={"trade": other_trade.code, "lat": PLATEAU[0], "lng": PLATEAU[1]},
        )
        unknown_trade = await http.get(
            f"/api/v1/artisans/{verified.id}/coverage",
            params={"trade": "inexistant", "lat": PLATEAU[0], "lng": PLATEAU[1]},
        )
        bad_point = await http.get(
            f"/api/v1/artisans/{verified.id}/coverage",
            params={"trade": trade.code, "lat": 120, "lng": 0},
        )

    assert not_verified.json() == {"eligible": False, "reason": "artisan_non_verifie"}
    assert wrong_trade.json() == {"eligible": False, "reason": "metier_non_exerce"}
    assert unknown_trade.status_code == 422
    assert bad_point.status_code == 422
