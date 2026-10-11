"""Consultation des paiements et isolation financière (BUILD_PLAN.md §3.5).

Les montants d'une intervention ne sont visibles que de ses deux parties
(et de l'admin) ; le client voit ses paiements, l'artisan ses gains nets et
les commissions prélevées.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from tests.factories import Engagement, make_user
from tests.payments_helpers import (
    AMOUNT,
    COMMISSION,
    NET,
    auth,
    client,
    init_payment,
    make_payable_engagement,
    override_dependencies,
    pay_online,
)


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession) -> Iterator[None]:
    with override_dependencies(db_session):
        yield


async def _same_artisan(db_session: AsyncSession, base: Engagement, amount: int) -> Engagement:
    """Une autre intervention payable pour le MÊME artisan."""
    other = await make_payable_engagement(db_session, labor_fcfa=amount, materials_fcfa=0)
    other.intervention.artisan_id = base.artisan.id
    await db_session.flush()
    return Engagement(
        client=other.client,
        artisan_user=base.artisan_user,
        artisan=base.artisan,
        intervention=other.intervention,
        conversation=other.conversation,
    )


async def test_both_parties_see_the_breakdown_a_third_party_sees_nothing(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)
    other_artisan = await make_user(db_session, role=Role.ARTISAN)
    admin = await make_user(db_session, role=Role.ADMIN)
    url = f"/api/v1/interventions/{engagement.intervention.id}"

    async with client() as http:
        await pay_online(http, db_session, engagement)
        as_client = await http.get(url, headers=auth(engagement.client))
        as_artisan = await http.get(url, headers=auth(engagement.artisan_user))
        as_admin = await http.get(url, headers=auth(admin))
        as_outsider = await http.get(url, headers=auth(outsider))
        as_other_artisan = await http.get(url, headers=auth(other_artisan))

    for response in (as_client, as_artisan, as_admin):
        assert response.status_code == 200
        payment = response.json()["payment"]
        assert payment["amount_fcfa"] == AMOUNT
        assert payment["commission"]["amount_fcfa"] == COMMISSION
        assert payment["net_fcfa"] == NET
        assert payment["status"] == "retenu"
    for response in (as_outsider, as_other_artisan):
        assert response.status_code == 403
        assert "payment" not in response.text
        assert str(AMOUNT) not in response.text


async def test_before_any_quote_there_is_no_amount_to_show(db_session: AsyncSession) -> None:
    from tests.factories import make_engagement

    engagement = await make_engagement(db_session)

    async with client() as http:
        response = await http.get(
            f"/api/v1/interventions/{engagement.intervention.id}",
            headers=auth(engagement.client),
        )

    assert response.json()["payment"] is None


async def test_a_client_sees_only_their_own_payments(db_session: AsyncSession) -> None:
    mine = await make_payable_engagement(db_session)
    theirs = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, mine, "cash")
        await init_payment(http, theirs, "cash")
        response = await http.get("/api/v1/payments/me", headers=auth(mine.client))
        as_artisan = await http.get("/api/v1/payments/me", headers=auth(mine.artisan_user))

    body = response.json()
    assert body["pagination"]["total"] == 1
    (item,) = body["items"]
    assert item["intervention_id"] == str(mine.intervention.id)
    assert item["amount_fcfa"] == AMOUNT
    assert item["channel"] == "cash"
    assert item["status"] == "reussi"
    assert item["artisan_name"] == "Idrissa Fall"
    assert as_artisan.status_code == 403


async def test_an_artisan_sees_net_earnings_and_every_commission(
    db_session: AsyncSession,
) -> None:
    online = await make_payable_engagement(db_session)  # 12 000 en ligne, terminé
    cash = await _same_artisan(db_session, online, 20_000)  # 20 000 espèces, terminé
    escrow = await _same_artisan(db_session, online, 5_000)  # 5 000 en ligne, en cours

    async with client() as http:
        await pay_online(http, db_session, online)
        await http.post(
            f"/api/v1/interventions/{online.intervention.id}/complete",
            headers=auth(online.client),
        )
        await init_payment(http, cash, "cash")
        await http.post(
            f"/api/v1/interventions/{cash.intervention.id}/complete",
            headers=auth(cash.client),
        )
        await pay_online(http, db_session, escrow)
        response = await http.get("/api/v1/payments/me/earnings", headers=auth(online.artisan_user))
        as_client = await http.get("/api/v1/payments/me/earnings", headers=auth(online.client))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"] == {
        "paid_out_fcfa": NET,  # 10 800 versés
        "payout_pending_fcfa": 0,
        "in_escrow_fcfa": 4_500,  # 5 000 - 10 %
        "commission_collected_fcfa": COMMISSION,  # 1 200 prélevés au versement
        "cash_received_fcfa": 20_000,
        "commission_due_fcfa": 2_000,  # 10 % des espèces, dus par l'artisan
    }
    assert body["pagination"]["total"] == 3
    by_id = {item["intervention_id"]: item for item in body["items"]}
    released = by_id[str(online.intervention.id)]["payment"]
    assert released["amount_fcfa"] == AMOUNT
    assert released["commission"]["amount_fcfa"] == COMMISSION
    assert released["net_fcfa"] == NET
    assert released["payout"]["status"] == "envoye"
    assert as_client.status_code == 403


async def test_an_artisan_without_payments_sees_zeros(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        response = await http.get(
            "/api/v1/payments/me/earnings", headers=auth(engagement.artisan_user)
        )

    body = response.json()
    assert body["items"] == []
    assert set(body["totals"].values()) == {0}


async def test_intervention_lists_carry_the_payment_summary(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)

    async with client() as http:
        await init_payment(http, engagement, "wave")
        response = await http.get("/api/v1/interventions/me", headers=auth(engagement.client))

    (item,) = response.json()["items"]
    assert item["payment"]["status"] == "en_attente"
    assert item["payment"]["checkout_url"]
