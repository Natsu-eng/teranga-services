"""Cycle complet rejet -> renvoi -> re-passage en pending (BUILD_PLAN.md,
espace admin, tâche 7) : combine l'upload artisan (Lot B,
`app.api.v1.artisans`) et la revue admin (Lot C, `app.api.v1.admin`) --
deux domaines distincts testés séparément ailleurs, exercés ici ensemble de
bout en bout.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import Verification
from app.models.enums import ArtisanVerifiedStatus, Role, VerificationDocType, VerificationStatus
from tests.factories import make_artisan_profile, make_user, make_verification

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path) -> Generator[None, None, None]:
    settings = get_settings().model_copy(update={"storage_local_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_settings, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_rejected_document_can_be_reuploaded_and_returns_to_pending(
    db_session: AsyncSession,
) -> None:
    admin = await make_user(db_session, role=Role.ADMIN)
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    # Selfie déjà approuvée : seule la CNI varie dans ce test. Sans ça, un
    # type requis totalement absent (jamais soumis) est traité comme
    # "en attente" par `compute_verified_status` (BUILD_PLAN.md §2.2, règle
    # 4) -- le rejet de la CNI se traduirait alors par `pending`, pas
    # `rejected`, ce qui masquerait le comportement qu'on veut isoler ici.
    await make_verification(
        db_session,
        artisan=artisan,
        doc_type=VerificationDocType.SELFIE,
        status=VerificationStatus.APPROVED,
    )
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await db_session.flush()
    artisan_token = encode_access_token(artisan_user)
    admin_headers = {"Authorization": f"Bearer {encode_access_token(admin)}"}
    artisan_headers = {"Authorization": f"Bearer {artisan_token}"}

    async with await _client() as client:
        # 1. L'artisan dépose une CNI.
        first_upload = await client.post(
            "/api/v1/artisans/me/documents",
            headers=artisan_headers,
            data={"doc_type": "cni"},
            files={"file": ("cni.png", _PNG_BYTES, "image/png")},
        )
        assert first_upload.status_code == 201
        first_id = first_upload.json()["id"]

        # 2. L'admin rejette, avec motif.
        reject = await client.post(
            f"/api/v1/admin/verifications/{first_id}/reject",
            json={"note": "Photo illisible, merci de renvoyer un scan net."},
            headers=admin_headers,
        )
        assert reject.status_code == 200
        assert reject.json()["artisan_verified_status"] == "rejected"

        # 3. L'artisan voit le motif dans son espace.
        my_docs_after_reject = await client.get(
            "/api/v1/artisans/me/documents", headers=artisan_headers
        )
        assert my_docs_after_reject.json()["verified_status"] == "rejected"
        rejected_doc = next(
            d for d in my_docs_after_reject.json()["documents"] if d["id"] == first_id
        )
        assert rejected_doc["status"] == "rejected"
        assert rejected_doc["note"] == "Photo illisible, merci de renvoyer un scan net."

        # 4. L'artisan renvoie un nouveau document du même type.
        second_upload = await client.post(
            "/api/v1/artisans/me/documents",
            headers=artisan_headers,
            data={"doc_type": "cni"},
            files={"file": ("cni-v2.png", _PNG_BYTES, "image/png")},
        )
        assert second_upload.status_code == 201
        second_id = second_upload.json()["id"]
        assert second_id != first_id
        assert second_upload.json()["status"] == "pending"

        # `created_at` est posé par `server_default=func.now()`, qui renvoie
        # l'heure de DÉBUT DE TRANSACTION en PostgreSQL (pas l'heure de
        # l'instruction) -- comme tout ce test tourne dans la même
        # transaction (harnais `db_session`), les deux lignes CNI
        # obtiendraient sinon un `created_at` identique, rendant le choix du
        # "plus récent par type" (`compute_verified_status`) ambigu. En
        # production, chaque upload est sa propre transaction (l'endpoint
        # commit), donc cette collision n'existe pas -- ici, on force
        # explicitement l'ordre pour tester le comportement réel.
        second_verification = (
            await db_session.execute(
                select(Verification).where(Verification.id == uuid.UUID(second_id))
            )
        ).scalar_one()
        second_verification.created_at = datetime.now(UTC) + timedelta(seconds=5)
        await db_session.flush()

        # 5. verified_status repasse à pending (plus "rejected") : c'est la
        # dernière ligne par type qui compte pour compute_verified_status.
        my_docs_after_reupload = await client.get(
            "/api/v1/artisans/me/documents", headers=artisan_headers
        )
        assert my_docs_after_reupload.json()["verified_status"] == "pending"

        # 6. Le nouveau document apparaît dans la file d'attente admin ;
        # l'admin peut désormais l'approuver.
        queue = await client.get(
            "/api/v1/admin/verifications", params={"status": "pending"}, headers=admin_headers
        )
        assert second_id in [item["id"] for item in queue.json()["items"]]

        approve = await client.post(
            f"/api/v1/admin/verifications/{second_id}/approve", headers=admin_headers
        )
        assert approve.status_code == 200
        # CNI et selfie approuvées toutes les deux : le cycle se termine
        # bien sur un artisan réellement vérifié.
        assert approve.json()["artisan_verified_status"] == "verified"
