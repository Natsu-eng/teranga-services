"""Tests d'intégration de l'upload de documents de vérification artisan
(BUILD_PLAN.md, onboarding artisan) :
`POST/GET /api/v1/artisans/me/documents`, `GET .../documents/{id}/content`.

Lot sensible (données d'identité) -- couvre explicitement : validation par
magic bytes (extension falsifiée rejetée), taille maximale, isolation par
rôle et par propriétaire, doc_url jamais une URL publique devinable, et la
dérivation de `verified_status` (none -> pending) au premier document déposé.
"""

from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encode_access_token
from app.db.session import get_session
from app.main import app
from app.models.artisan import ArtisanProfile
from app.models.enums import ArtisanVerifiedStatus, Role
from app.models.user import User
from app.services.storage import LocalStorageBackend, get_storage_backend
from tests.factories import make_artisan_profile, make_user

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 32
_FAKE_JPEG_BYTES = b"ceci n'est pas une image, juste renomme en .jpg"


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_test_session


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path) -> Generator[None, None, None]:
    """Redirige le backend de stockage vers un répertoire temporaire propre
    à chaque test -- jamais le vrai `backend/var/` pendant les tests."""
    settings = get_settings().model_copy(update={"storage_local_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield


def _override_settings(**update: object) -> None:
    """Combine avec l'isolation de stockage déjà active (`_isolate_storage`)
    plutôt que de repartir des settings par défaut -- une écriture disque
    accidentelle pendant un test doit toujours atterrir dans `tmp_path`."""
    current = app.dependency_overrides[get_settings]()
    updated = current.model_copy(update=update)
    app.dependency_overrides[get_settings] = lambda: updated


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_settings, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user)}"}


async def _upload(
    client: AsyncClient, *, token: str, doc_type: str, content: bytes, filename: str = "doc.png"
) -> Response:
    return await client.post(
        "/api/v1/artisans/me/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"doc_type": doc_type},
        files={"file": (filename, content, "image/png")},
    )


async def test_nominal_upload_creates_pending_document(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

    assert response.status_code == 201
    body = response.json()
    assert body["doc_type"] == "cni"
    assert body["status"] == "pending"
    assert "doc_url" not in body  # jamais exposé -- référence interne uniquement


async def test_pdf_accepted_for_cni(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await _upload(
            client, token=token, doc_type="cni", content=_PDF_BYTES, filename="cni.pdf"
        )

    assert response.status_code == 201


async def test_pdf_rejected_for_selfie(db_session: AsyncSession) -> None:
    """Un selfie ne peut jamais être un PDF -- restriction par type de
    document, pas seulement par famille de fichier acceptée globalement."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await _upload(
            client, token=token, doc_type="selfie", content=_PDF_BYTES, filename="selfie.pdf"
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FICHIER_TYPE_INVALIDE"


async def test_falsified_extension_is_rejected_by_magic_bytes(db_session: AsyncSession) -> None:
    """Le coeur de l'exigence de sécurité : un fichier texte renommé en
    .jpg, avec un Content-Type déclaré "image/png", doit être rejeté --
    la décision repose sur le contenu réel, jamais sur le nom ni le header
    déclaré par le client."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        response = await _upload(
            client, token=token, doc_type="cni", content=_FAKE_JPEG_BYTES, filename="cni.jpg"
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FICHIER_TYPE_INVALIDE"


async def test_oversized_file_is_rejected(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    _override_settings(storage_max_upload_bytes=16)

    async with await _client() as client:
        response = await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FICHIER_TROP_VOLUMINEUX"


async def test_client_role_cannot_upload_document(db_session: AsyncSession) -> None:
    client_user = await make_user(db_session, role=Role.CLIENT)
    token = encode_access_token(client_user)

    async with await _client() as client:
        response = await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_INSUFFISANT"


async def test_unauthenticated_cannot_upload_document() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/artisans/me/documents",
            data={"doc_type": "cni"},
            files={"file": ("doc.png", _PNG_BYTES, "image/png")},
        )

    assert response.status_code == 401


async def test_artisan_cannot_list_another_artisans_documents(db_session: AsyncSession) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN, full_name="Owner")
    owner = await make_artisan_profile(db_session, user=owner_user)
    other_user = await make_user(db_session, role=Role.ARTISAN, full_name="Other")
    await make_artisan_profile(db_session, user=other_user)

    async with await _client() as client:
        await _upload(
            client, token=encode_access_token(owner_user), doc_type="cni", content=_PNG_BYTES
        )
        other_response = await client.get(
            "/api/v1/artisans/me/documents", headers=_auth_headers(other_user)
        )

    assert other_response.status_code == 200
    assert other_response.json()["documents"] == []  # jamais les documents de `owner`
    assert owner.id != other_user.id  # sanity : deux artisans bien distincts


async def test_artisan_cannot_read_another_artisans_document_content(
    db_session: AsyncSession,
) -> None:
    owner_user = await make_user(db_session, role=Role.ARTISAN, full_name="Owner")
    await make_artisan_profile(db_session, user=owner_user)
    other_user = await make_user(db_session, role=Role.ARTISAN, full_name="Other")
    await make_artisan_profile(db_session, user=other_user)

    async with await _client() as client:
        upload_response = await _upload(
            client, token=encode_access_token(owner_user), doc_type="cni", content=_PNG_BYTES
        )
        document_id = upload_response.json()["id"]

        forbidden_response = await client.get(
            f"/api/v1/artisans/me/documents/{document_id}/content",
            headers=_auth_headers(other_user),
        )

    assert forbidden_response.status_code == 404
    assert forbidden_response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_owner_can_read_own_document_content_byte_for_byte(
    db_session: AsyncSession,
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        upload_response = await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)
        document_id = upload_response.json()["id"]

        content_response = await client.get(
            f"/api/v1/artisans/me/documents/{document_id}/content",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert content_response.status_code == 200
    assert content_response.content == _PNG_BYTES
    assert content_response.headers["content-type"] == "image/png"


async def test_doc_url_is_never_a_public_or_guessable_url(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

    from app.models.artisan import Verification

    stmt = select(Verification.doc_url).where(Verification.artisan_id == artisan.id)
    doc_url = (await db_session.execute(stmt)).scalar_one()

    assert not doc_url.startswith("http://")
    assert not doc_url.startswith("https://")
    # Doit rester une référence interne (clé de stockage), pas une URL.


async def test_verified_status_moves_from_none_to_pending_on_first_upload(
    db_session: AsyncSession,
) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await db_session.flush()
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        before = await client.get(
            "/api/v1/artisans/me/documents", headers=_auth_headers(artisan_user)
        )
        assert before.json()["verified_status"] == "none"

        await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

        after = await client.get(
            "/api/v1/artisans/me/documents", headers=_auth_headers(artisan_user)
        )

    assert after.json()["verified_status"] == "pending"

    stmt = select(ArtisanProfile.verified_status).where(ArtisanProfile.id == artisan.id)
    persisted = (await db_session.execute(stmt)).scalar_one()
    assert persisted == ArtisanVerifiedStatus.PENDING


async def test_verified_status_reaches_verified_once_both_required_docs_approved(
    db_session: AsyncSession,
) -> None:
    """Upload seul ne suffit jamais à VERIFIED (statut `pending` tant qu'un
    admin n'a pas approuvé) -- vérifie que l'upload ne court-circuite pas
    la revue humaine (Lot C, hors périmètre ici)."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    artisan = await make_artisan_profile(db_session, user=artisan_user)
    artisan.verified_status = ArtisanVerifiedStatus.NONE
    await db_session.flush()
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)
        await _upload(client, token=token, doc_type="selfie", content=_PNG_BYTES)
        listing = await client.get(
            "/api/v1/artisans/me/documents", headers=_auth_headers(artisan_user)
        )

    assert listing.json()["verified_status"] == "pending"
    assert len(listing.json()["documents"]) == 2


async def test_local_storage_never_writes_under_backend_var_during_tests(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Confirme que la fixture `_isolate_storage` redirige effectivement les
    écritures -- garde-fou contre une régression qui ferait fuiter des
    fichiers de test dans le vrai répertoire de stockage local."""
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        await _upload(client, token=token, doc_type="cni", content=_PNG_BYTES)

    written_files = list(tmp_path.rglob("*.png"))
    assert len(written_files) == 1

    settings = get_settings().model_copy(update={"storage_local_dir": str(tmp_path)})
    backend = get_storage_backend(settings)
    assert isinstance(backend, LocalStorageBackend)
    assert backend._base_dir == tmp_path.resolve()  # noqa: SLF001
