"""Signalement des avis par l'artisan et modération admin (BUILD_PLAN.md §3.6).

Un avis n'est jamais supprimé. Signalé : il reste visible et compté jusqu'à
la décision. Masqué : retiré de la liste publique et de la note, de façon
journalisée et réversible.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_access_token
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.audit import AuditLog
from app.models.enums import AuditAction, InterventionStatus, ReviewStatus, Role
from app.models.review import Review
from app.models.user import User
from app.services.reviews import recalculate_artisan_rating
from tests.factories import Engagement, make_engagement, make_review, make_user


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


REASON = "Ce client n'a jamais fait appel à moi, avis mensonger."


async def _reviewed_artisan(
    db_session: AsyncSession, ratings: list[int], *, comment: str = "Avis de test."
) -> tuple[Engagement, list[Review]]:
    """Un artisan et un avis par note, chacun sur sa propre intervention
    terminée ; la note dénormalisée est calculée comme en production."""
    first = await make_engagement(db_session, status=InterventionStatus.TERMINEE)
    reviews = []
    for index, rating in enumerate(ratings):
        engagement = (
            first
            if index == 0
            else await make_engagement(db_session, status=InterventionStatus.TERMINEE)
        )
        engagement.intervention.artisan_id = first.artisan.id
        await db_session.flush()
        reviews.append(
            await make_review(
                db_session,
                intervention=engagement.intervention,
                author=engagement.client,
                artisan=first.artisan,
                rating=rating,
                comment=comment,
            )
        )
    await recalculate_artisan_rating(db_session, first.artisan.id)
    await db_session.flush()
    return first, reviews


async def _report(http: AsyncClient, artisan_user: User, review: Review) -> Response:
    return await http.post(
        f"/api/v1/artisans/me/reviews/{review.id}/report",
        json={"reason": REASON},
        headers=_auth(artisan_user),
    )


async def _rating(db_session: AsyncSession, artisan: ArtisanProfile) -> tuple[Decimal | None, int]:
    await db_session.refresh(artisan)
    return artisan.rating_avg, artisan.review_count


async def test_a_reported_review_stays_visible_and_counted_until_decided(
    db_session: AsyncSession,
) -> None:
    engagement, (bad, good) = await _reviewed_artisan(db_session, [1, 5])
    before = await _rating(db_session, engagement.artisan)

    async with _client() as http:
        reported = await _report(http, engagement.artisan_user, bad)
        twice = await _report(http, engagement.artisan_user, bad)
        public = await http.get(f"/api/v1/artisans/{engagement.artisan.id}/reviews")
        mine = await http.get("/api/v1/artisans/me/reviews", headers=_auth(engagement.artisan_user))

    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "signale"
    assert reported.json()["report_reason"] == REASON
    assert reported.json()["can_report"] is False
    assert twice.status_code == 409
    assert twice.json()["error"]["code"] == "AVIS_DEJA_SIGNALE"
    # Signaler ne fait rien disparaître : même note, même liste publique.
    assert await _rating(db_session, engagement.artisan) == before == (Decimal("3.00"), 2)
    statuses = {item["id"]: item["status"] for item in public.json()["items"]}
    assert statuses == {str(bad.id): "signale", str(good.id): "publie"}
    assert {item["id"]: item["can_report"] for item in mine.json()["items"]} == {
        str(bad.id): False,
        str(good.id): True,
    }


async def test_reporting_is_reserved_to_the_concerned_artisan_with_a_reason(
    db_session: AsyncSession,
) -> None:
    engagement, (review,) = await _reviewed_artisan(db_session, [2])
    other_artisan = (await make_engagement(db_session)).artisan_user

    async with _client() as http:
        too_short = await http.post(
            f"/api/v1/artisans/me/reviews/{review.id}/report",
            json={"reason": "Faux"},
            headers=_auth(engagement.artisan_user),
        )
        by_other_artisan = await _report(http, other_artisan, review)
        by_client = await _report(http, engagement.client, review)

    assert too_short.status_code == 422
    # Un autre artisan : 404, comme un id inconnu (on ne révèle rien).
    assert by_other_artisan.status_code == 404
    assert by_client.status_code == 403
    await db_session.refresh(review)
    assert review.status is ReviewStatus.PUBLIE
    assert review.reported_at is None


async def test_hiding_recalculates_the_rating_and_restoring_reverts_it(
    db_session: AsyncSession,
) -> None:
    engagement, (bad, good) = await _reviewed_artisan(db_session, [1, 5])
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")

    async with _client() as http:
        await _report(http, engagement.artisan_user, bad)
        no_reason = await http.post(
            f"/api/v1/admin/reviews/{bad.id}/hide", json={"reason": "Non"}, headers=_auth(admin)
        )
        hidden = await http.post(
            f"/api/v1/admin/reviews/{bad.id}/hide",
            json={"reason": "Avis sans rapport avec l'intervention réalisée."},
            headers=_auth(admin),
        )
        rating_hidden = await _rating(db_session, engagement.artisan)
        public = await http.get(f"/api/v1/artisans/{engagement.artisan.id}/reviews")
        mine = await http.get("/api/v1/artisans/me/reviews", headers=_auth(engagement.artisan_user))
        hide_again = await http.post(
            f"/api/v1/admin/reviews/{bad.id}/hide",
            json={"reason": "Deuxième tentative de masquage."},
            headers=_auth(admin),
        )
        reported_after_hide = await _report(http, engagement.artisan_user, bad)
        restored = await http.post(
            f"/api/v1/admin/reviews/{bad.id}/restore",
            json={"note": "Après vérification, l'avis est légitime."},
            headers=_auth(admin),
        )
        rating_restored = await _rating(db_session, engagement.artisan)
        restore_again = await http.post(
            f"/api/v1/admin/reviews/{bad.id}/restore", json={}, headers=_auth(admin)
        )

    assert no_reason.status_code == 422
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["status"] == "masque"
    # Le signalement reste en historique sur l'avis.
    assert hidden.json()["report_reason"] == REASON
    assert rating_hidden == (Decimal("5.00"), 1)
    assert [item["id"] for item in public.json()["items"]] == [str(good.id)]
    # L'artisan voit la décision de modération (transparence).
    assert {item["id"]: item["status"] for item in mine.json()["items"]}[str(bad.id)] == "masque"
    assert hide_again.json()["error"]["code"] == "AVIS_DEJA_MASQUE"
    assert reported_after_hide.status_code == 409
    assert restored.json()["status"] == "publie"
    assert rating_restored == (Decimal("3.00"), 2)
    assert restore_again.json()["error"]["code"] == "AVIS_DEJA_PUBLIE"


async def test_each_moderation_decision_is_journaled(db_session: AsyncSession) -> None:
    engagement, (review,) = await _reviewed_artisan(db_session, [1])
    admin = await make_user(db_session, role=Role.ADMIN, full_name="Awa Admin")

    async with _client() as http:
        await _report(http, engagement.artisan_user, review)
        await http.post(
            f"/api/v1/admin/reviews/{review.id}/hide",
            json={"reason": "Propos injurieux envers l'artisan."},
            headers=_auth(admin),
        )
        await http.post(f"/api/v1/admin/reviews/{review.id}/restore", json={}, headers=_auth(admin))
        detail = await http.get(
            f"/api/v1/admin/artisans/{engagement.artisan.id}", headers=_auth(admin)
        )

    entries = list(
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.target_id == review.id)
                .order_by(AuditLog.created_at)
            )
        ).scalars()
    )
    # Le signalement est l'acte de l'artisan (porté par l'avis lui-même) ;
    # le journal trace les décisions de l'admin.
    assert [e.action for e in entries] == [AuditAction.REVIEW_HIDE, AuditAction.REVIEW_RESTORE]
    assert all(e.actor_id == admin.id for e in entries)
    assert entries[0].details == {
        "reason": "Propos injurieux envers l'artisan.",
        "previous_status": "signale",
        "rating": 1,
        "artisan_id": str(engagement.artisan.id),
    }
    assert entries[1].details["previous_status"] == "masque"
    # L'historique de l'artisan, côté admin, inclut ces décisions.
    history = [entry["action"] for entry in detail.json()["history"]]
    assert history[:2] == ["review.restore", "review.hide"]


async def test_admin_review_list_puts_reported_first_and_filters(
    db_session: AsyncSession,
) -> None:
    # L'avis signalé est le PREMIER créé : il remonte quand même en tête.
    engagement, (reported, other) = await _reviewed_artisan(
        db_session, [2, 4], comment="Zq travail_soigné"
    )
    admin = await make_user(db_session, role=Role.ADMIN)

    async with _client() as http:
        before = await http.get("/api/v1/admin/overview", headers=_auth(admin))
        await _report(http, engagement.artisan_user, reported)
        after = await http.get("/api/v1/admin/overview", headers=_auth(admin))
        by_artisan = await http.get(
            "/api/v1/admin/reviews",
            params={"artisan_id": str(engagement.artisan.id)},
            headers=_auth(admin),
        )
        only_reported = await http.get(
            "/api/v1/admin/reviews",
            params={"status": "signale", "artisan_id": str(engagement.artisan.id)},
            headers=_auth(admin),
        )
        literal = await http.get(
            "/api/v1/admin/reviews", params={"q": "travail_soign"}, headers=_auth(admin)
        )
        wildcard = await http.get(
            "/api/v1/admin/reviews", params={"q": "Zq%soign"}, headers=_auth(admin)
        )

    assert after.json()["reported_reviews"] == before.json()["reported_reviews"] + 1
    items = by_artisan.json()["items"]
    assert [item["id"] for item in items] == [str(reported.id), str(other.id)]
    # L'admin voit l'auteur réel, pas le nom abrégé public.
    assert items[0]["author_name"] == "Awa Diop"
    assert items[0]["artisan_name"] == "Idrissa Fall"
    assert [item["id"] for item in only_reported.json()["items"]] == [str(reported.id)]
    assert {item["id"] for item in literal.json()["items"]} == {str(other.id), str(reported.id)}
    assert wildcard.json()["items"] == []


async def test_moderation_is_reserved_to_admins(db_session: AsyncSession) -> None:
    engagement, (review,) = await _reviewed_artisan(db_session, [1])

    async with _client() as http:
        responses = [
            await http.get("/api/v1/admin/reviews", headers=_auth(engagement.client)),
            await http.get("/api/v1/admin/reviews", headers=_auth(engagement.artisan_user)),
            await http.post(
                f"/api/v1/admin/reviews/{review.id}/hide",
                json={"reason": "Je veux faire disparaître cet avis."},
                headers=_auth(engagement.artisan_user),
            ),
            await http.post(
                f"/api/v1/admin/reviews/{review.id}/restore",
                json={},
                headers=_auth(engagement.client),
            ),
        ]
        anonymous = await http.get("/api/v1/admin/reviews")

    assert [r.status_code for r in responses] == [403] * 4
    assert anonymous.status_code == 401
    await db_session.refresh(review)
    assert review.status is ReviewStatus.PUBLIE
