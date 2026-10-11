"""Messagerie in-app, routes REST (`/api/v1/conversations`).

Vérifie le contrat ET les garanties : isolation stricte des fils (un tiers
reçoit exactement la même réponse qu'un fil inexistant), écriture
persistante, curseur `since` (repli polling), masquage des coordonnées de
bout en bout, non-lus, images réencodées et réservées aux participants.
"""

from collections.abc import AsyncGenerator, Generator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.enums import InterventionStatus, Role
from app.models.user import User
from app.services.contact_masking import PHONE_PLACEHOLDER
from tests.factories import Engagement, make_engagement, make_message, make_user
from tests.images import EXIF_GPS_IFD, EXIF_MAKE, make_jpeg


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> Generator[None, None, None]:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _isolate_attachments(tmp_path: Path) -> Generator[None, None, None]:
    """Les images jointes sont écrites dans un répertoire temporaire du test,
    jamais dans le stockage de dev."""
    settings = get_settings().model_copy(
        update={"message_attachment_storage_local_dir": str(tmp_path)}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


def _override_settings(**changes: Any) -> None:
    current = app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: current.model_copy(update=changes)


async def _send(client: AsyncClient, engagement: Engagement, sender: User, body: str) -> Any:
    response = await client.post(
        f"/api/v1/conversations/{engagement.conversation.id}/messages",
        json={"body": body},
        headers=_auth(sender),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ Isolation


async def test_participants_read_the_conversation(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        as_client = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}", headers=_auth(engagement.client)
        )
        as_artisan = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}",
            headers=_auth(engagement.artisan_user),
        )

    assert as_client.status_code == 200
    assert as_client.json()["other_party"]["display_name"] == "Idrissa Fall"
    assert as_client.json()["other_party"]["role"] == "artisan"
    assert as_artisan.status_code == 200
    assert as_artisan.json()["other_party"]["display_name"] == "Awa Diop"
    assert as_artisan.json()["can_send"] is True


async def test_third_party_gets_the_same_403_as_a_missing_conversation(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)
    missing_id = "00000000-0000-4000-8000-000000000000"

    async with _client() as client:
        foreign = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}", headers=_auth(outsider)
        )
        missing = await client.get(f"/api/v1/conversations/{missing_id}", headers=_auth(outsider))
        read_messages = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            headers=_auth(outsider),
        )
        write = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": "Bonjour"},
            headers=_auth(outsider),
        )

    # Strictement identiques : rien ne révèle l'existence du fil.
    assert foreign.status_code == missing.status_code == 403
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "CONVERSATION_ACCES_INTERDIT"
    assert read_messages.status_code == 403
    assert write.status_code == 403


async def test_admin_is_excluded_from_messaging(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    admin = await make_user(db_session, role=Role.ADMIN)

    async with _client() as client:
        response = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}", headers=_auth(admin)
        )

    assert response.status_code == 403


async def test_anonymous_access_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        response = await client.get(f"/api/v1/conversations/{engagement.conversation.id}")

    assert response.status_code == 401


# ------------------------------------------------------------------ Envoi / lecture


async def test_send_persists_and_returns_the_message(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        sent = await _send(client, engagement, engagement.client, "  Bonjour, la fuite continue.  ")
        history = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            headers=_auth(engagement.artisan_user),
        )

    assert sent["body"] == "Bonjour, la fuite continue."
    assert sent["sender_id"] == str(engagement.client.id)
    assert sent["contact_masked"] is False
    assert sent["has_attachment"] is False
    assert [m["id"] for m in history.json()["items"]] == [sent["id"]]


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
async def test_empty_message_is_refused(db_session: AsyncSession, body: str) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        response = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": body},
            headers=_auth(engagement.client),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MESSAGE_VIDE"


async def test_too_long_message_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    max_length = get_settings().messaging_body_max_length

    async with _client() as client:
        response = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": "a" * (max_length + 1)},
            headers=_auth(engagement.client),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MESSAGE_TROP_LONG"


async def test_refused_intervention_closes_the_conversation_to_new_messages(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session, status=InterventionStatus.ANNULEE)

    async with _client() as client:
        meta = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}", headers=_auth(engagement.client)
        )
        response = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            json={"body": "Toujours là ?"},
            headers=_auth(engagement.client),
        )

    assert meta.json()["can_send"] is False
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_FERMEE"


async def test_since_returns_only_newer_messages(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    first = await make_message(
        db_session, conversation=engagement.conversation, sender=engagement.client, body="Un"
    )
    second = await make_message(
        db_session,
        conversation=engagement.conversation,
        sender=engagement.artisan_user,
        body="Deux",
    )
    third = await make_message(
        db_session, conversation=engagement.conversation, sender=engagement.client, body="Trois"
    )

    async with _client() as client:
        response = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            params={"since": first.seq},
            headers=_auth(engagement.client),
        )
        nothing_new = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            params={"since": third.seq},
            headers=_auth(engagement.client),
        )

    assert [m["seq"] for m in response.json()["items"]] == [second.seq, third.seq]
    assert nothing_new.json()["items"] == []


async def test_history_pages_backwards_with_before(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    messages = [
        await make_message(
            db_session,
            conversation=engagement.conversation,
            sender=engagement.client,
            body=f"Message {index}",
        )
        for index in range(5)
    ]

    async with _client() as client:
        latest = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            params={"limit": 2},
            headers=_auth(engagement.client),
        )
        older = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            params={"limit": 2, "before": messages[3].seq},
            headers=_auth(engagement.client),
        )
        both = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            params={"before": 10, "since": 1},
            headers=_auth(engagement.client),
        )

    # Toujours du plus ancien au plus récent.
    assert [m["body"] for m in latest.json()["items"]] == ["Message 3", "Message 4"]
    assert latest.json()["has_more"] is True
    assert [m["body"] for m in older.json()["items"]] == ["Message 1", "Message 2"]
    assert older.json()["has_more"] is True
    assert both.status_code == 422
    assert both.json()["error"]["code"] == "CURSEURS_INCOMPATIBLES"


# ------------------------------------------------------------------ Masquage


async def test_phone_number_is_masked_before_storage_and_delivery(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        sent = await _send(
            client, engagement, engagement.artisan_user, "Appelez-moi au +221 77 123 45 67 !"
        )
        seen_by_client = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages",
            headers=_auth(engagement.client),
        )

    assert sent["body"] == f"Appelez-moi au {PHONE_PLACEHOLDER} !"
    assert sent["contact_masked"] is True
    item = seen_by_client.json()["items"][0]
    assert item["body"] == f"Appelez-moi au {PHONE_PLACEHOLDER} !"
    assert item["contact_masked"] is True
    assert "123 45 67" not in seen_by_client.text


async def test_ordinary_numbers_are_never_masked(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        sent = await _send(
            client, engagement, engagement.artisan_user, "Il faut 2 robinets de 15 mm, 75 000 FCFA."
        )

    assert sent["body"] == "Il faut 2 robinets de 15 mm, 75 000 FCFA."
    assert sent["contact_masked"] is False


# ------------------------------------------------------------------ Liste et non-lus


async def test_list_shows_last_message_and_unread_counts(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        await _send(client, engagement, engagement.artisan_user, "Bonjour")
        await _send(client, engagement, engagement.artisan_user, "Je passe demain à 10h")
        as_client = await client.get("/api/v1/conversations/me", headers=_auth(engagement.client))
        as_artisan = await client.get(
            "/api/v1/conversations/me", headers=_auth(engagement.artisan_user)
        )
        unread_client = await client.get(
            "/api/v1/conversations/me/unread-count", headers=_auth(engagement.client)
        )
        unread_artisan = await client.get(
            "/api/v1/conversations/me/unread-count", headers=_auth(engagement.artisan_user)
        )

    client_item = as_client.json()["items"][0]
    assert client_item["id"] == str(engagement.conversation.id)
    assert client_item["unread_count"] == 2
    assert client_item["last_message"]["body"] == "Je passe demain à 10h"
    assert client_item["last_message"]["from_me"] is False
    # L'auteur n'a jamais de non-lu pour ses propres messages.
    assert as_artisan.json()["items"][0]["unread_count"] == 0
    assert as_artisan.json()["items"][0]["last_message"]["from_me"] is True
    assert unread_client.json() == {"count": 2}
    assert unread_artisan.json() == {"count": 0}


async def test_list_is_sorted_by_most_recent_activity(db_session: AsyncSession) -> None:
    first = await make_engagement(db_session)
    # Même client, second artisan : deux fils pour le même compte.
    second = await make_engagement(db_session, client=first.client)

    async with _client() as client:
        await _send(client, first, first.client, "Premier fil")
        await _send(client, second, first.client, "Second fil")
        before = await client.get("/api/v1/conversations/me", headers=_auth(first.client))
        await _send(client, first, first.client, "Le premier fil redevient le plus actif")
        after = await client.get("/api/v1/conversations/me", headers=_auth(first.client))

    assert [item["id"] for item in before.json()["items"]] == [
        str(second.conversation.id),
        str(first.conversation.id),
    ]
    assert [item["id"] for item in after.json()["items"]] == [
        str(first.conversation.id),
        str(second.conversation.id),
    ]


async def test_list_never_shows_other_users_conversations(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)

    async with _client() as client:
        await _send(client, engagement, engagement.client, "Fil privé")
        theirs = await client.get("/api/v1/conversations/me", headers=_auth(outsider))

    assert theirs.json()["items"] == []
    assert theirs.json()["pagination"]["total"] == 0


async def test_list_can_be_filtered_by_artisan(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        same = await client.get(
            "/api/v1/conversations/me",
            params={"artisan_id": str(engagement.artisan.id)},
            headers=_auth(engagement.client),
        )
        other = await client.get(
            "/api/v1/conversations/me",
            params={"artisan_id": "00000000-0000-4000-8000-000000000000"},
            headers=_auth(engagement.client),
        )

    assert [item["id"] for item in same.json()["items"]] == [str(engagement.conversation.id)]
    assert other.json()["items"] == []


async def test_mark_read_clears_unread_and_never_moves_backwards(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        await _send(client, engagement, engagement.artisan_user, "Un")
        last = await _send(client, engagement, engagement.artisan_user, "Deux")
        read = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/read",
            json={"last_read_seq": last["seq"]},
            headers=_auth(engagement.client),
        )
        backwards = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/read",
            json={"last_read_seq": 0},
            headers=_auth(engagement.client),
        )
        beyond = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/read",
            json={"last_read_seq": last["seq"] + 1_000},
            headers=_auth(engagement.client),
        )
        unread = await client.get(
            "/api/v1/conversations/me/unread-count", headers=_auth(engagement.client)
        )

    assert read.json()["my_last_read_seq"] == last["seq"]
    assert backwards.json()["my_last_read_seq"] == last["seq"]
    # Jamais au-delà du dernier message réellement présent.
    assert beyond.json()["my_last_read_seq"] == last["seq"]
    assert unread.json() == {"count": 0}


# ------------------------------------------------------------------ Images jointes


def _image_from(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


async def test_photo_is_reencoded_without_metadata_and_served_to_participants_only(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)
    outsider = await make_user(db_session, role=Role.CLIENT)
    original = make_jpeg(64, 48, with_gps=True)
    assert _image_from(original).getexif().get_ifd(EXIF_GPS_IFD)  # garde du test

    async with _client() as client:
        sent = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages/image",
            files={"file": ("ma-cuisine.jpg", original, "image/jpeg")},
            data={"caption": "Voici la fuite, mon numéro 77 123 45 67"},
            headers=_auth(engagement.client),
        )
        url = (
            f"/api/v1/conversations/{engagement.conversation.id}"
            f"/messages/{sent.json()['id']}/attachment"
        )
        for_artisan = await client.get(url, headers=_auth(engagement.artisan_user))
        for_outsider = await client.get(url, headers=_auth(outsider))

    assert sent.status_code == 201, sent.text
    message = sent.json()
    assert message["has_attachment"] is True
    assert message["attachment_content_type"] == "image/jpeg"
    # La légende est masquée comme un texte.
    assert message["body"] == f"Voici la fuite, mon numéro {PHONE_PLACEHOLDER}"
    assert message["contact_masked"] is True

    assert for_artisan.status_code == 200
    assert for_artisan.headers["content-type"] == "image/jpeg"
    assert for_artisan.headers["cache-control"] == "private, no-store"
    served = _image_from(for_artisan.content)
    exif = served.getexif()
    assert not exif.get_ifd(EXIF_GPS_IFD)
    assert EXIF_MAKE not in exif
    assert for_artisan.content != original

    assert for_outsider.status_code == 403


async def test_non_image_attachment_is_refused(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        pdf = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages/image",
            files={"file": ("devis.jpg", b"%PDF-1.7 faux jpeg", "image/jpeg")},
            headers=_auth(engagement.client),
        )
        empty = await client.post(
            f"/api/v1/conversations/{engagement.conversation.id}/messages/image",
            files={"file": ("vide.jpg", b"", "image/jpeg")},
            headers=_auth(engagement.client),
        )

    assert pdf.status_code == 422
    assert pdf.json()["error"]["code"] == "PIECE_JOINTE_TYPE_INVALIDE"
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "PIECE_JOINTE_VIDE"


async def test_text_message_has_no_attachment_to_serve(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    async with _client() as client:
        sent = await _send(client, engagement, engagement.client, "Juste du texte")
        response = await client.get(
            f"/api/v1/conversations/{engagement.conversation.id}/messages/{sent['id']}/attachment",
            headers=_auth(engagement.client),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PIECE_JOINTE_INTROUVABLE"


# ------------------------------------------------------------------ Rate limiting


async def test_sending_is_rate_limited_per_user(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    _override_settings(rate_limit_message_send_per_user_max=2)

    async with _client() as client:
        statuses = [
            (
                await client.post(
                    f"/api/v1/conversations/{engagement.conversation.id}/messages",
                    json={"body": f"Message {index}"},
                    headers=_auth(engagement.client),
                )
            ).status_code
            for index in range(3)
        ]

    assert statuses == [201, 201, 429]
