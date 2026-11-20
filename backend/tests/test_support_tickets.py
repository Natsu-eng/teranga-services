"""Aide : demandes au support (`/api/v1/support`, `/api/v1/admin/support`).

Application réelle en ASGI, base de dev dans une transaction annulée.
Propriété des demandes, intervention d'autrui refusée sans fuite, limite de
débit, message conservé tel qu'écrit (non masqué : lu seulement par l'auteur
et les admins), e-mail sans fuite, journal d'audit, garde admin.
"""

import logging
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditTargetType, Role, SupportCategory
from app.models.support import SupportTicket
from app.models.user import User
from app.services import admin_notifications
from app.services.admin_notifications import build_support_ticket_email
from app.services.contact_masking import PHONE_PLACEHOLDER
from app.services.email import EmailSendError, OutgoingEmail
from app.services.rate_limit import SlidingWindowRateLimiter, get_support_ticket_rate_limiter
from tests.factories import make_engagement, make_user

MESSAGE = "Je n'arrive pas à modifier mon nom sur mon profil."
PHONE_MESSAGE = "Rappelez-moi au 77 123 45 67, mon paiement n'apparaît pas."


class RecordingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[OutgoingEmail] = []
        self.error = error

    async def send(self, email: OutgoingEmail) -> None:
        if self.error:
            raise self.error
        self.sent.append(email)


@pytest.fixture(autouse=True)
def _app(db_session: AsyncSession) -> Generator[None, None, None]:
    settings = get_settings().model_copy(update={"admin_notification_emails": []})

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_support_ticket_rate_limiter] = lambda: limiter
    yield
    app.dependency_overrides.clear()


def _override_settings(**changes: Any) -> None:
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(update=changes)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _create(
    http: AsyncClient,
    user: User,
    *,
    message: str = MESSAGE,
    category: str = "compte",
    intervention_id: uuid.UUID | None = None,
) -> Response:
    body: dict[str, Any] = {"category": category, "message": message}
    if intervention_id is not None:
        body["intervention_id"] = str(intervention_id)
    return await http.post("/api/v1/support/tickets", json=body, headers=_auth(user))


async def _mine(http: AsyncClient, user: User) -> list[dict[str, Any]]:
    response = await http.get("/api/v1/support/tickets", headers=_auth(user))
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# ------------------------------------------------------------- création


@pytest.mark.parametrize("role", [Role.CLIENT, Role.ARTISAN])
async def test_a_client_or_an_artisan_can_ask_for_help(
    db_session: AsyncSession, role: Role
) -> None:
    user = await make_user(db_session, role=role)
    async with _client() as http:
        response = await _create(http, user, category="bug")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category"] == "bug" and body["status"] == "ouvert"
    assert body["message"] == MESSAGE
    assert body["admin_reply"] is None and body["intervention_id"] is None


async def test_the_message_is_kept_as_written(db_session: AsyncSession) -> None:
    """Non masqué : seuls l'auteur et les admins le lisent ; l'utilisateur peut
    y laisser un moyen de le recontacter."""
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as http:
        response = await _create(http, user, message=PHONE_MESSAGE, category="paiement")
        (item,) = await _mine(http, user)

    assert response.json()["message"] == PHONE_MESSAGE
    assert item["message"] == PHONE_MESSAGE
    stored = await db_session.scalar(
        select(SupportTicket.message).where(SupportTicket.author_id == user.id)
    )
    assert stored == PHONE_MESSAGE and PHONE_PLACEHOLDER not in stored


@pytest.mark.parametrize(
    "body",
    [
        {"category": "compte", "message": "x" * 9},  # sous le minimum (10)
        {"category": "compte", "message": "x" * 2001},
        {"category": "inconnue", "message": MESSAGE},
        {"message": MESSAGE},
    ],
)
async def test_input_is_bounded(db_session: AsyncSession, body: dict[str, Any]) -> None:
    user = await make_user(db_session, role=Role.CLIENT)
    async with _client() as http:
        response = await http.post("/api/v1/support/tickets", json=body, headers=_auth(user))
    assert response.status_code == 422


async def test_only_signed_in_clients_and_artisans(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with _client() as http:
        anonymous = await http.post(
            "/api/v1/support/tickets", json={"category": "compte", "message": MESSAGE}
        )
        as_admin = await _create(http, admin)
        anonymous_list = await http.get("/api/v1/support/tickets")

    assert anonymous.status_code == 401 and anonymous_list.status_code == 401
    assert as_admin.status_code == 403


# ------------------------------------------------- intervention : à l'auteur seulement


@pytest.mark.parametrize("side", ["client", "artisan"])
async def test_an_own_intervention_can_be_attached(db_session: AsyncSession, side: str) -> None:
    engagement = await make_engagement(db_session)
    author = engagement.client if side == "client" else engagement.artisan_user
    async with _client() as http:
        response = await _create(
            http, author, category="utilisateur", intervention_id=engagement.intervention.id
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["intervention_id"] == str(engagement.intervention.id)
    assert (
        body["intervention_trade_label"] == engagement.intervention.service_request.trade.label_fr
    )


async def test_someone_elses_intervention_is_refused_like_an_unknown_one(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)
    stranger = await make_user(db_session, role=Role.CLIENT)
    async with _client() as http:
        foreign = await _create(http, stranger, intervention_id=engagement.intervention.id)
        unknown = await _create(http, stranger, intervention_id=uuid.uuid4())

    # Aucune différence observable : l'existence de l'intervention ne fuit pas.
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert (
        await db_session.scalar(
            select(SupportTicket.id).where(SupportTicket.author_id == stranger.id)
        )
        is None
    )


# ------------------------------------------------------------- propriété


async def test_each_user_only_ever_sees_their_own_requests(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, role=Role.CLIENT)
    bob = await make_user(db_session, role=Role.ARTISAN)
    async with _client() as http:
        await _create(http, alice, message="Demande d'Alice, à propos de mon compte.")
        await _create(http, bob, message="Demande de Bob, à propos d'un paiement.")
        alice_items = await _mine(http, alice)
        bob_items = await _mine(http, bob)

    assert [item["message"] for item in alice_items] == ["Demande d'Alice, à propos de mon compte."]
    assert [item["message"] for item in bob_items] == ["Demande de Bob, à propos d'un paiement."]
    # Le format « auteur » n'expose jamais l'identité de quiconque.
    assert "author_id" not in alice_items[0] and "author_name" not in alice_items[0]


# ------------------------------------------------------------- limite de débit


async def test_requests_are_rate_limited_per_user(db_session: AsyncSession) -> None:
    _override_settings(rate_limit_support_ticket_per_user_max=2)
    user = await make_user(db_session, role=Role.CLIENT)
    other = await make_user(db_session, role=Role.CLIENT)
    async with _client() as http:
        statuses = [(await _create(http, user)).status_code for _ in range(3)]
        other_status = (await _create(http, other)).status_code
        stored = await _mine(http, user)

    assert statuses == [201, 201, 429]
    assert len(stored) == 2  # au-delà de la limite, rien n'est enregistré
    assert other_status == 201  # la limite est par utilisateur


# ------------------------------------------------------------- e-mail admin


async def test_admins_are_alerted_without_any_content(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)
    _override_settings(admin_notification_emails=["admin@teranga.example"])
    user = await make_user(db_session, role=Role.ARTISAN, full_name="Idrissa Fall")
    async with _client() as http:
        response = await _create(http, user, message=PHONE_MESSAGE, category="paiement")

    assert response.status_code == 201
    (email,) = provider.sent
    assert "Catégorie : Paiement" in email.body
    assert "Envoyée par : un artisan" in email.body
    assert "/admin/support" in email.body
    for leak in ("77", "Rappelez", "paiement n'apparaît", "Idrissa", user.phone, PHONE_PLACEHOLDER):
        assert leak not in email.body and leak not in email.subject


async def test_an_email_failure_never_fails_the_request(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = RecordingProvider(EmailSendError("Brevo HTTP 401 (unauthorized)"))
    monkeypatch.setattr(admin_notifications, "get_email_provider", lambda _s: provider)
    _override_settings(admin_notification_emails=["admin@teranga.example"])
    user = await make_user(db_session, role=Role.CLIENT)
    with caplog.at_level(logging.INFO):
        async with _client() as http:
            response = await _create(http, user)

    assert response.status_code == 201
    assert "Notification admin (demande d'aide) NON envoyée : Brevo HTTP 401" in caplog.text


@pytest.mark.parametrize(
    ("category", "label"),
    [
        (SupportCategory.COMPTE, "Compte"),
        (SupportCategory.UTILISATEUR, "Un artisan ou un client"),
        (SupportCategory.PAIEMENT, "Paiement"),
        (SupportCategory.BUG, "Problème technique"),
        (SupportCategory.AUTRE, "Autre"),
    ],
)
def test_every_category_has_a_readable_label(category: SupportCategory, label: str) -> None:
    settings = get_settings().model_copy(update={"admin_notification_emails": ["a@b.example"]})
    body = build_support_ticket_email(category, Role.CLIENT, settings).body
    assert f"Catégorie : {label}\n" in body


def test_the_categories_are_exactly_the_agreed_ones() -> None:
    assert {c.value for c in SupportCategory} == {
        "compte",
        "utilisateur",
        "paiement",
        "bug",
        "autre",
    }


# ------------------------------------------------------------- admin


async def test_admin_routes_are_admin_only(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    artisan = await make_user(db_session, role=Role.ARTISAN)
    async with _client() as http:
        ticket_id = (await _create(http, client_user)).json()["id"]
        anonymous = await http.get("/api/v1/admin/support/tickets")
        statuses = [
            (await http.get("/api/v1/admin/support/tickets", headers=_auth(user))).status_code
            for user in (client_user, artisan)
        ]
        reply = await http.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/reply",
            json={"reply": "Je m'en occupe."},
            headers=_auth(client_user),
        )

    assert anonymous.status_code == 401
    assert statuses == [403, 403]
    assert reply.status_code == 403


async def test_admin_replies_resolves_and_the_author_sees_the_answer(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    user = await make_user(db_session, role=Role.CLIENT, full_name="Awa Diop")
    async with _client() as http:
        ticket_id = (await _create(http, user, message=PHONE_MESSAGE, category="paiement")).json()[
            "id"
        ]
        queue = await http.get("/api/v1/admin/support/tickets", headers=_auth(admin))
        reply = await http.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/reply",
            json={"reply": "Paiement retrouvé, tout est en ordre."},
            headers=_auth(admin),
        )
        resolved = await http.get(
            "/api/v1/admin/support/tickets?status=resolu", headers=_auth(admin)
        )
        (mine,) = await _mine(http, user)
        again = await http.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/reply",
            json={"reply": "Autre réponse."},
            headers=_auth(admin),
        )

    queued = next(item for item in queue.json()["items"] if item["id"] == ticket_id)
    assert queued["author_name"] == "Awa Diop" and queued["author_role"] == "client"
    # Message tel qu'écrit pour l'admin ; jamais le numéro du COMPTE de l'auteur.
    assert queued["message"] == PHONE_MESSAGE
    assert "phone" not in queued and user.phone not in queue.text
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "resolu" and reply.json()["resolved_at"] is not None
    assert ticket_id in [item["id"] for item in resolved.json()["items"]]
    assert mine["status"] == "resolu"
    assert mine["admin_reply"] == "Paiement retrouvé, tout est en ordre."
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DEMANDE_AIDE_DEJA_RESOLUE"

    (entry,) = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.target_type == AuditTargetType.SUPPORT_TICKET,
                AuditLog.target_id == uuid.UUID(ticket_id),
            )
        )
    ).all()
    assert entry.action is AuditAction.SUPPORT_TICKET_REPLY and entry.actor_id == admin.id
    assert entry.details["resolved"] is True and entry.details["category"] == "paiement"
    # Jamais le message de l'utilisateur ni son nom dans le journal.
    assert "message" not in entry.details
    assert "Rappelez" not in str(entry.details) and "Awa" not in str(entry.details)


async def test_a_holding_reply_keeps_the_request_open(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    user = await make_user(db_session, role=Role.ARTISAN)
    async with _client() as http:
        ticket_id = (await _create(http, user)).json()["id"]
        first = await http.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/reply",
            json={"reply": "Pouvez-vous préciser l'écran concerné ?", "resolve": False},
            headers=_auth(admin),
        )
        second = await http.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/reply",
            json={"reply": "Corrigé, merci du signalement."},
            headers=_auth(admin),
        )

    assert first.json()["status"] == "ouvert" and first.json()["admin_reply"]
    assert second.json()["status"] == "resolu"
    entries = (
        await db_session.scalars(select(AuditLog).where(AuditLog.target_id == uuid.UUID(ticket_id)))
    ).all()
    assert [entry.details["resolved"] for entry in entries] == [False, True]


async def test_replying_to_an_unknown_request_is_a_404(db_session: AsyncSession) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    async with _client() as http:
        response = await http.post(
            f"/api/v1/admin/support/tickets/{uuid.uuid4()}/reply",
            json={"reply": "Réponse."},
            headers=_auth(admin),
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEMANDE_AIDE_INTROUVABLE"
