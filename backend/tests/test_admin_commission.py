"""Grille de commission administrée (BUILD_PLAN.md §2.2, §3.6).

Preuve centrale : ajouter un taux ne touche JAMAIS une intervention qui a
déjà figé le sien, ni sa commission -- même calculée après le changement.
On ajoute, on ne modifie ni ne supprime : aucune route PUT/PATCH/DELETE.
"""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.audit import AuditLog
from app.models.commission import CommissionRate
from app.models.enums import AuditAction, InterventionStatus, Role
from app.models.trade import Trade
from app.models.user import User
from app.services import admin_commission as admin_commission_service
from app.services import payments as payments_service
from app.services.commission import resolve_effective_commission_rate
from tests.factories import make_engagement, make_trade, make_user


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Iterator[None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_session_factory] = lambda: _scope
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _add(http: AsyncClient, admin: User, **payload: object) -> Response:
    return await http.post("/api/v1/admin/commission-rates", json=payload, headers=_auth(admin))


def _snapshot(rate: CommissionRate) -> tuple[object, ...]:
    return (rate.id, rate.rate_bps, rate.trade_id, rate.tier, rate.effective_from)


async def test_adding_a_rate_never_touches_frozen_interventions_or_commissions(
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    admin = await make_user(db_session, role=Role.ADMIN)
    # Deux interventions figées sur le taux d'origine (10 %) : l'une a déjà sa
    # commission, l'autre la calculera APRÈS l'ajout du nouveau taux.
    with_fee = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    without_fee = await make_engagement(db_session, status=InterventionStatus.EN_COURS)
    original = await db_session.get(CommissionRate, with_fee.intervention.commission_rate_id)
    assert original is not None and original.trade_id is not None
    trade_id = original.trade_id
    without_fee.intervention.commission_rate_id = original.id
    for engagement in (with_fee, without_fee):
        engagement.intervention.agreed_amount_fcfa = 25_000
    await db_session.flush()
    for engagement in (with_fee, without_fee):
        # Relations chargées explicitement (pas de chargement implicite en async).
        await db_session.refresh(engagement.intervention, ["commission_rate", "platform_fees"])
    fee = payments_service.ensure_commission_fee(
        db_session, with_fee.intervention, settings=settings
    )
    await db_session.flush()
    assert fee is not None
    fee_before = (fee.id, fee.amount_fcfa, fee.commission_rate_id)
    rate_before = _snapshot(original)
    trade = await db_session.get(Trade, trade_id)
    assert trade is not None

    async with _client() as http:
        added = await _add(http, admin, rate_bps=2000, trade_code=trade.code)
        frozen_view = await http.get(
            f"/api/v1/interventions/{with_fee.intervention.id}", headers=_auth(with_fee.client)
        )
        grid = await http.get(
            "/api/v1/admin/commission-rates",
            params={"trade_code": trade.code},
            headers=_auth(admin),
        )

    assert added.status_code == 201, added.text
    await db_session.refresh(original)
    await db_session.refresh(fee)
    # Le taux d'origine : mêmes valeurs, même début ; seule sa FIN est posée.
    assert _snapshot(original) == rate_before
    assert original.effective_to is not None
    assert (
        fee_before
        == (fee.id, fee.amount_fcfa, fee.commission_rate_id)
        == (
            fee.id,
            2_500,
            original.id,
        )
    )
    assert frozen_view.json()["commission_rate_bps"] == 1000
    # Commission calculée APRÈS le changement : toujours sur le taux figé.
    late_fee = payments_service.ensure_commission_fee(
        db_session, without_fee.intervention, settings=settings
    )
    assert late_fee is not None
    assert (late_fee.amount_fcfa, late_fee.commission_rate_id) == (2_500, original.id)
    # Une NOUVELLE intervention résoudrait, elle, le nouveau taux.
    assert (await resolve_effective_commission_rate(db_session, trade_id=trade_id)).rate_bps == 2000
    rows = {row["id"]: row for row in grid.json()["items"]}
    assert rows[str(original.id)]["state"] == "archive"
    assert rows[str(original.id)]["interventions_count"] == 2
    assert rows[added.json()["id"]]["state"] == "en_vigueur"
    assert rows[added.json()["id"]]["interventions_count"] == 0


async def test_a_programmed_rate_bounds_the_new_one_and_the_grid_stays_continuous(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    trade = await make_trade(db_session)
    future = datetime.now(UTC) + timedelta(days=10)

    async with _client() as http:
        first = await _add(http, admin, rate_bps=1200, trade_code=trade.code)
        programmed = await _add(
            http, admin, rate_bps=900, trade_code=trade.code, effective_from=future.isoformat()
        )
        between = await _add(http, admin, rate_bps=1100, trade_code=trade.code)
        grid = await http.get(
            "/api/v1/admin/commission-rates",
            params={"trade_code": trade.code},
            headers=_auth(admin),
        )

    assert [r.status_code for r in (first, programmed, between)] == [201] * 3
    assert programmed.json()["state"] == "programme"
    # Le taux ajouté entre-temps s'arrête là où le programmé commence.
    assert datetime.fromisoformat(between.json()["effective_to"]) == future
    items = grid.json()["items"]
    assert [item["rate_bps"] for item in items] == [900, 1100, 1200]
    assert [item["state"] for item in items] == ["programme", "en_vigueur", "archive"]
    # Continuité : chaque fin est exactement le début du suivant.
    by_start = sorted(items, key=lambda item: item["effective_from"])
    for earlier, later in zip(by_start, by_start[1:], strict=False):
        assert earlier["effective_to"] == later["effective_from"]
    assert by_start[-1]["effective_to"] is None


async def test_invalid_rates_are_refused_with_clear_errors(db_session: AsyncSession) -> None:
    settings = get_settings()
    admin = await make_user(db_session, role=Role.ADMIN)
    trade = await make_trade(db_session)
    start = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    async with _client() as http:
        tier = await _add(http, admin, rate_bps=800, trade_code=trade.code, tier="verified")
        past = await _add(
            http,
            admin,
            rate_bps=800,
            trade_code=trade.code,
            effective_from=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )
        too_high = await _add(
            http, admin, rate_bps=settings.commission_rate_max_bps + 1, trade_code=trade.code
        )
        out_of_bounds = await _add(http, admin, rate_bps=10_001, trade_code=trade.code)
        naive = await _add(
            http, admin, rate_bps=800, trade_code=trade.code, effective_from="2030-01-01T00:00:00"
        )
        unknown_trade = await _add(http, admin, rate_bps=800, trade_code="metier-inexistant")
        await _add(http, admin, rate_bps=800, trade_code=trade.code, effective_from=start)
        same_start = await _add(
            http, admin, rate_bps=700, trade_code=trade.code, effective_from=start
        )

    assert tier.status_code == 422
    assert tier.json()["error"]["code"] == "PALIER_NON_APPLIQUE"
    assert past.json()["error"]["code"] == "DATE_EFFET_PASSEE"
    assert too_high.json()["error"]["code"] == "TAUX_TROP_ELEVE"
    assert out_of_bounds.status_code == 422
    assert naive.status_code == 422
    assert unknown_trade.status_code == 404
    assert same_start.status_code == 409
    assert same_start.json()["error"]["code"] == "CHEVAUCHEMENT_TAUX"


async def test_a_concurrent_overlap_is_a_clear_409_never_a_raw_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Course : un autre admin a validé un taux de même portée entre-temps.
    On simule une lecture qui ne l'a pas vu ; la contrainte d'exclusion
    tranche et l'API répond 409 CHEVAUCHEMENT_TAUX, sans rien écrire."""
    admin = await make_user(db_session, role=Role.ADMIN)
    trade = await make_trade(db_session)
    db_session.add(
        CommissionRate(rate_bps=1000, trade_id=trade.id, effective_from=datetime.now(UTC))
    )
    await db_session.flush()

    async def _stale_scope(*_: object, **__: object) -> list[CommissionRate]:
        return []

    monkeypatch.setattr(admin_commission_service, "_lock_scope", _stale_scope)
    async with _client() as http:
        response = await _add(http, admin, rate_bps=1500, trade_code=trade.code)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHEVAUCHEMENT_TAUX"
    rates = (
        await db_session.execute(select(CommissionRate).where(CommissionRate.trade_id == trade.id))
    ).scalars()
    assert [rate.rate_bps for rate in rates] == [1000]
    journaled = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.action == AuditAction.COMMISSION_RATE_CREATE)
                .where(AuditLog.details["trade_code"].astext == trade.code)
            )
        )
        .scalars()
        .all()
    )
    assert journaled == []


async def test_each_new_rate_is_journaled_with_the_closed_one(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")
    trade = await make_trade(db_session)

    async with _client() as http:
        first = await _add(http, admin, rate_bps=1000, trade_code=trade.code)
        second = await _add(
            http, admin, rate_bps=1300, trade_code=trade.code, note="Nouvelle grille 2027."
        )

    entry = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.target_id == uuid.UUID(second.json()["id"]))
        )
    ).scalar_one()
    assert entry.action is AuditAction.COMMISSION_RATE_CREATE
    assert entry.actor_id == admin.id
    assert entry.details["rate_bps"] == 1300
    assert entry.details["trade_code"] == trade.code
    assert entry.details["note"] == "Nouvelle grille 2027."
    assert entry.details["closed_rate"] == {"id": first.json()["id"], "previous_effective_to": None}


async def test_the_grid_is_admin_only_and_offers_no_edit_or_delete(
    db_session: AsyncSession,
) -> None:
    client = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_user(db_session, role=Role.ARTISAN)

    async with _client() as http:
        responses = [
            await http.get("/api/v1/admin/commission-rates", headers=_auth(client)),
            await http.get("/api/v1/admin/commission-rates", headers=_auth(artisan)),
            await _add(http, client, rate_bps=0),
            await _add(http, artisan, rate_bps=0),
        ]
        anonymous = await http.get("/api/v1/admin/commission-rates")

    assert [r.status_code for r in responses] == [403] * 4
    assert anonymous.status_code == 401
    # Ajout seul : aucune route ne modifie ni ne supprime un taux.
    paths = app.openapi()["paths"]
    rate_paths = {path: set(ops) for path, ops in paths.items() if "commission-rates" in path}
    assert rate_paths == {"/api/v1/admin/commission-rates": {"get", "post"}}
