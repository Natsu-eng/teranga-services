"""Litiges, lot A : fenêtre après la fin des travaux, issues honnêtes en
espèces, masquage des motifs, avis suspendu, alerte admin, statistiques
(app/services/disputes.py, dispute_rules.py, payments.py, reviews).

Application réelle en ASGI, base de dev dans une transaction annulée.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.enums import (
    InterventionStatus,
    PaymentStatus,
    PlatformFeeStatus,
    Role,
    ServiceRequestStatus,
)
from app.models.intervention import Intervention, InterventionDispute
from app.models.request import ServiceRequest
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import payments as payments_repository
from app.services import admin_notifications
from app.services.admin_notifications import build_dispute_opened_email, notify_dispute_opened
from app.services.contact_masking import PHONE_PLACEHOLDER
from app.services.email import EmailSendError, OutgoingEmail
from tests.factories import Engagement, make_engagement, make_user
from tests.payments_helpers import (
    auth,
    client,
    commission_of,
    init_payment,
    make_payable_engagement,
    only_payment,
    override_dependencies,
    pay_online,
    update_settings,
)

REASON = "Une fuite est réapparue le lendemain, le joint n'a pas tenu."
PHONE_REASON = "Rappelez-moi au 77 123 45 67, la fuite continue depuis hier."


@pytest.fixture(autouse=True)
def _overrides(db_session: AsyncSession) -> object:
    # Aucun e-mail réel : la notification admin est observée séparément.
    with override_dependencies(db_session, admin_notification_emails=[]):
        yield


async def _complete(http: AsyncClient, engagement: Engagement) -> Response:
    response = await http.post(
        f"/api/v1/interventions/{engagement.intervention.id}/complete",
        headers=auth(engagement.client),
    )
    assert response.status_code == 200, response.text
    return response


async def _dispute(
    http: AsyncClient, engagement: Engagement, user: User, reason: str = REASON
) -> Response:
    return await http.post(
        f"/api/v1/interventions/{engagement.intervention.id}/dispute",
        json={"reason": reason},
        headers=auth(user),
    )


async def _resolve(
    http: AsyncClient, engagement: Engagement, admin: User, outcome: str
) -> Response:
    response = await http.post(
        f"/api/v1/admin/disputes/{engagement.intervention.id}/resolve",
        json={"outcome": outcome, "note": "Photos et échanges examinés."},
        headers=auth(admin),
    )
    assert response.status_code == 200, response.text
    return response


async def _completed_cash(db_session: AsyncSession, http: AsyncClient) -> Engagement:
    engagement = await make_payable_engagement(db_session)
    await init_payment(http, engagement, "cash")
    await _complete(http, engagement)
    return engagement


async def _age_completion(db_session: AsyncSession, engagement: Engagement, hours: float) -> None:
    """Recule la fin des travaux de `hours` heures (le temps passe)."""
    intervention = await db_session.get(Intervention, engagement.intervention.id)
    assert intervention is not None and intervention.completed_at is not None
    intervention.completed_at -= timedelta(hours=hours)
    await db_session.flush()


async def _request_status(db_session: AsyncSession, engagement: Engagement) -> ServiceRequestStatus:
    status = await db_session.scalar(
        select(ServiceRequest.status).where(
            ServiceRequest.id == engagement.intervention.service_request_id
        )
    )
    assert status is not None
    return status


# ----------------------------------------------------- fenêtre après les travaux


async def test_completion_announces_the_window_and_a_dispute_can_follow(
    db_session: AsyncSession,
) -> None:
    async with client() as http:
        engagement = await make_payable_engagement(db_session)
        await init_payment(http, engagement, "cash")
        completed = (await _complete(http, engagement)).json()
        opened = await _dispute(http, engagement, engagement.client)

    completed_at = datetime.fromisoformat(completed["completed_at"])
    window = timedelta(hours=get_settings().dispute_window_hours)
    assert completed["can_open_dispute"] is True
    assert datetime.fromisoformat(completed["dispute_deadline"]) == completed_at + window
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["status"] == "litige"
    assert body["can_open_dispute"] is False and body["dispute_deadline"] is None


async def test_the_artisan_can_also_report_after_completion(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        response = await _dispute(http, engagement, engagement.artisan_user)

    assert response.status_code == 200
    assert response.json()["dispute"]["opened_by"] == "artisan"


async def test_after_the_window_the_report_is_refused_clearly(db_session: AsyncSession) -> None:
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        await _age_completion(db_session, engagement, get_settings().dispute_window_hours + 1)
        response = await _dispute(http, engagement, engagement.client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LITIGE_DELAI_DEPASSE"


async def test_a_disabled_window_allows_disputes_only_during_the_work(
    db_session: AsyncSession,
) -> None:
    update_settings(dispute_window_hours=0)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        response = await _dispute(http, engagement, engagement.client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LITIGE_DELAI_DEPASSE"


async def test_an_online_payment_already_paid_out_cannot_be_disputed(
    db_session: AsyncSession,
) -> None:
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _complete(http, engagement)  # séquestre libéré, versement envoyé
        response = await _dispute(http, engagement, engagement.client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LITIGE_PAIEMENT_DEJA_VERSE"


async def test_only_one_dispute_per_intervention_even_after_a_decision(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        assert (await _dispute(http, engagement, engagement.client)).status_code == 200
        released = (await _resolve(http, engagement, admin, "libere")).json()
        again = await _dispute(http, engagement, engagement.artisan_user)

    assert released["can_open_dispute"] is False
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "LITIGE_DEJA_OUVERT"


async def test_no_dispute_before_the_work_starts(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.ACCEPTEE)
    async with client() as http:
        response = await _dispute(http, engagement, engagement.client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSITION_INTERVENTION_INVALIDE"


# ---------------------------------------------------- issues honnêtes (espèces)


async def test_release_after_completion_keeps_the_original_completion_date(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        await _age_completion(db_session, engagement, 5)
        intervention = await db_session.get(Intervention, engagement.intervention.id)
        assert intervention is not None
        original = intervention.completed_at
        await _dispute(http, engagement, engagement.client)
        body = (await _resolve(http, engagement, admin, "libere")).json()

    assert body["status"] == "terminee"
    assert datetime.fromisoformat(body["completed_at"]) == original
    payment = await only_payment(db_session, engagement)
    assert payment.status is PaymentStatus.REUSSI
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.DUE


async def test_client_side_decision_on_cash_after_completion_is_honest(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        await _dispute(http, engagement, engagement.client)
        body = (await _resolve(http, engagement, admin, "rembourse")).json()

    assert body["status"] == "annulee"
    assert body["cancellation"]["kind"] == "arbitrage"
    # Téranga ne détient pas les espèces : le paiement n'est ni « remboursé »
    # ni effacé de l'historique.
    assert body["payment"]["status"] == "reussi"
    assert (await only_payment(db_session, engagement)).status is PaymentStatus.REUSSI
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE
    # Les travaux ont eu lieu : pas de demande rouverte à d'autres artisans.
    assert await _request_status(db_session, engagement) is not ServiceRequestStatus.OUVERTE


async def test_client_side_decision_during_the_work_reopens_the_request(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        await init_payment(http, engagement, "cash")
        await _dispute(http, engagement, engagement.client)
        body = (await _resolve(http, engagement, admin, "rembourse")).json()

    assert body["payment"]["status"] == "reussi"
    assert await _request_status(db_session, engagement) is ServiceRequestStatus.OUVERTE
    fee = await commission_of(db_session, engagement)
    assert fee is not None and fee.status is PlatformFeeStatus.ANNULEE


async def test_client_side_decision_without_any_payment(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        await _dispute(http, engagement, engagement.artisan_user)
        body = (await _resolve(http, engagement, admin, "rembourse")).json()

    assert body["status"] == "annulee"
    assert body["payment"]["status"] is None


async def test_online_escrow_is_still_really_refunded(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        await pay_online(http, db_session, engagement)
        await _dispute(http, engagement, engagement.client)
        body = (await _resolve(http, engagement, admin, "rembourse")).json()

    assert body["payment"]["status"] == "rembourse"


# ------------------------------------------------------------- masquage


async def test_a_phone_number_in_a_dispute_reason_is_masked(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        response = await _dispute(http, engagement, engagement.client, PHONE_REASON)

    reason = response.json()["dispute"]["reason"]
    assert PHONE_PLACEHOLDER in reason and "77 123 45 67" not in reason
    stored = await db_session.scalar(
        select(InterventionDispute.reason).where(
            InterventionDispute.intervention_id == engagement.intervention.id
        )
    )
    assert stored is not None and "77 123 45 67" not in stored


async def test_a_phone_number_in_a_cancellation_reason_is_masked(db_session: AsyncSession) -> None:
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/cancel",
            json={"reason": PHONE_REASON},
            headers=auth(engagement.artisan_user),
        )

    reason = response.json()["cancellation"]["reason"]
    assert PHONE_PLACEHOLDER in reason and "77 123 45 67" not in reason


async def test_a_phone_number_in_a_decline_reason_is_masked(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.PROPOSEE)
    async with client() as http:
        response = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/decline",
            json={"reason": "Indisponible, appelez le 77 123 45 67."},
            headers=auth(engagement.artisan_user),
        )

    assert response.status_code == 200, response.text
    assert "77 123 45 67" not in response.json()["cancellation"]["reason"]


# ------------------------------------------------- avis suspendu pendant le litige


async def _public_reviews(http: AsyncClient, engagement: Engagement) -> dict[str, Any]:
    response = await http.get(f"/api/v1/artisans/{engagement.artisan.id}/reviews")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.parametrize("outcome", ["libere", "rembourse"])
async def test_a_review_is_hidden_during_the_dispute_and_back_after_the_decision(
    db_session: AsyncSession, outcome: str
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        posted = await http.post(
            f"/api/v1/interventions/{engagement.intervention.id}/review",
            json={"rating": 2, "comment": "Travail à reprendre."},
            headers=auth(engagement.client),
        )
        assert posted.status_code == 201, posted.text
        before = await _public_reviews(http, engagement)
        await _dispute(http, engagement, engagement.artisan_user)
        during = await _public_reviews(http, engagement)
        await db_session.refresh(engagement.artisan)
        rating_during = engagement.artisan.rating_avg
        await _resolve(http, engagement, admin, outcome)
        after = await _public_reviews(http, engagement)
        await db_session.refresh(engagement.artisan)

    assert before["pagination"]["total"] == 1
    assert during["pagination"]["total"] == 0 and during["items"] == []
    assert rating_during is None
    assert after["pagination"]["total"] == 1
    assert engagement.artisan.rating_avg is not None and float(engagement.artisan.rating_avg) == 2


# ------------------------------------------------------------- statistiques


async def test_completed_counters_exclude_a_job_while_it_is_disputed(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with client() as http:
        engagement = await _completed_cash(db_session, http)
        artisan_id = engagement.artisan.id

        async def snapshot() -> tuple[int, int, int]:
            totals = await payments_repository.artisan_earnings_totals(db_session, artisan_id)
            return (
                await artisans_repository.count_completed_interventions(db_session, artisan_id),
                totals["cash_received_fcfa"],
                totals["commission_due_fcfa"],
            )

        done = await snapshot()
        await _dispute(http, engagement, engagement.client)
        disputed = await snapshot()
        await _resolve(http, engagement, admin, "libere")
        released = await snapshot()

    assert done[0] == 1 and done[1] > 0 and done[2] > 0
    # Effet TEMPORAIRE (documenté) : le temps de la décision, les travaux ne
    # comptent plus comme terminés, ni leurs montants.
    assert disputed == (0, 0, 0)
    assert released == done


# ------------------------------------------------------------- alerte admin


class RecordingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[OutgoingEmail] = []
        self.error = error

    async def send(self, email: OutgoingEmail) -> None:
        if self.error:
            raise self.error
        self.sent.append(email)


async def test_admins_are_alerted_after_the_report_without_any_detail(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)
    update_settings(admin_notification_emails=["admin@teranga.example"])
    engagement = await make_payable_engagement(db_session)
    async with client() as http:
        response = await _dispute(http, engagement, engagement.client, PHONE_REASON)

    assert response.status_code == 200
    (email,) = provider.sent
    assert email.to == ("admin@teranga.example",)
    assert "/admin/litiges" in email.body
    assert "Signalé par : le client" in email.body
    trade = engagement.intervention.service_request.trade.label_fr
    assert f"Métier : {trade}" in email.body
    for leak in (
        "fuite",
        "77",
        PHONE_PLACEHOLDER,
        engagement.client.full_name,
        engagement.client.phone,
    ):
        assert leak not in email.body and leak not in email.subject


async def test_an_email_failure_never_fails_the_report(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = RecordingProvider(EmailSendError("Brevo HTTP 401 (unauthorized)"))
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)
    update_settings(admin_notification_emails=["admin@teranga.example"])
    engagement = await make_payable_engagement(db_session)
    with caplog.at_level(logging.INFO):
        async with client() as http:
            response = await _dispute(http, engagement, engagement.artisan_user)

    assert response.status_code == 200
    assert response.json()["status"] == "litige"
    assert "Notification admin (litige ouvert) NON envoyée : Brevo HTTP 401" in caplog.text


async def test_no_recipient_means_no_email() -> None:
    provider = RecordingProvider()
    settings = get_settings().model_copy(update={"admin_notification_emails": []})
    await notify_dispute_opened("Plomberie", Role.CLIENT, settings, provider=provider)
    assert provider.sent == []


def test_the_dispute_email_names_the_reporter_by_role_only() -> None:
    settings = get_settings().model_copy(
        update={
            "admin_notification_emails": ["admin@teranga.example"],
            "frontend_public_base_url": "https://teranga.example/",
        }
    )
    email = build_dispute_opened_email("Plomberie", Role.ARTISAN, settings)
    assert "Signalé par : l'artisan" in email.body
    assert "https://teranga.example/admin/litiges" in email.body
