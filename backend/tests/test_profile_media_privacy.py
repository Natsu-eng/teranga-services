"""Confidentialité du stockage (BUILD_PLAN.md, lot `feat/profile-media`) :
preuve que le régime PUBLIC (avatar, couverture) et le régime PRIVÉ
(documents de vérification, Lot B) ne se recoupent jamais.

Contrairement aux autres tests d'upload de ce lot, ceux-ci n'isolent PAS
`avatar_storage_local_dir` vers un `tmp_path` : ils vérifient l'accessibilité
publique *réelle*, à travers le montage `StaticFiles` fixé par `app.main` au
démarrage du process -- une isolation vers `tmp_path` (qui ne peut pas
changer ce montage, déjà figé) rendrait ce test toujours vert même si le
montage était cassé. Les fichiers écrits sont supprimés en fin de test.
"""

import re
import uuid
from collections.abc import AsyncGenerator, Generator
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
from app.models.enums import Role
from app.services.rate_limit import SlidingWindowRateLimiter, get_profile_media_upload_rate_limiter
from app.services.storage import resolve_local_dir
from tests.factories import make_artisan_profile, make_user
from tests.images import make_png

_PNG_BYTES = make_png()
# Clé de stockage : `{prefixe éventuel}{uuid4 hex, 32 caractères}.{extension}`
# (le préfixe "cover-" distingue juste une couverture d'un avatar dans le
# même répertoire public, voir app/services/covers.py) -- jamais un id
# séquentiel ni un nom fourni par le client, donc non devinable.
_RANDOM_KEY_RE = re.compile(r"(?:cover-)?([0-9a-f]{32})\.(png|jpg)$")


@pytest.fixture(autouse=True)
def _override_session(db_session: AsyncSession) -> None:
    async def _get_test_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Une seule instance, réutilisée par le lambda (voir
    # test_artisan_avatar_endpoint.py pour le raisonnement complet).
    fresh_rate_limiter = SlidingWindowRateLimiter()
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_profile_media_upload_rate_limiter] = lambda: fresh_rate_limiter


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_profile_media_upload_rate_limiter, None)


async def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _path_from_public_url(url: str) -> str:
    """`http://localhost:8000/static/avatars/xxx` -> `/static/avatars/xxx` --
    seul le chemin compte pour router sur le même `app` via ASGITransport,
    l'origine (BACKEND_PUBLIC_BASE_URL) n'est qu'une convention d'affichage
    côté client, pas une contrainte réseau ici."""
    return "/static/" + url.split("/static/", 1)[1]


async def test_uploaded_avatar_is_publicly_reachable(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    settings = get_settings()
    written_file: Path | None = None

    try:
        async with await _client() as client:
            upload = await client.post(
                "/api/v1/artisans/me/avatar",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
            )
            avatar_url = upload.json()["avatar_url"]
            key = avatar_url.rsplit("/static/avatars/", 1)[1]
            written_file = resolve_local_dir(settings.avatar_storage_local_dir) / key

            public_response = await client.get(_path_from_public_url(avatar_url))

        assert public_response.status_code == 200
        # Jamais les octets envoyés : l'image réencodée par le serveur
        # (PNG opaque -> JPEG, métadonnées retirées).
        assert public_response.content != _PNG_BYTES
        assert public_response.content[:3] == b"\xff\xd8\xff"
    finally:
        if written_file is not None:
            written_file.unlink(missing_ok=True)


async def test_uploaded_cover_is_publicly_reachable(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    settings = get_settings()
    written_file: Path | None = None

    try:
        async with await _client() as client:
            upload = await client.post(
                "/api/v1/artisans/me/cover",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cover.png", _PNG_BYTES, "image/png")},
            )
            cover_url = upload.json()["cover_url"]
            key = cover_url.rsplit("/static/avatars/", 1)[1]
            written_file = resolve_local_dir(settings.avatar_storage_local_dir) / key

            public_response = await client.get(_path_from_public_url(cover_url))

        assert public_response.status_code == 200
        # Jamais les octets envoyés : l'image réencodée par le serveur
        # (PNG opaque -> JPEG, métadonnées retirées).
        assert public_response.content != _PNG_BYTES
        assert public_response.content[:3] == b"\xff\xd8\xff"
    finally:
        if written_file is not None:
            written_file.unlink(missing_ok=True)


async def test_private_verification_document_is_not_reachable_under_the_public_mount(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Non-régression de la confidentialité du Lot B : un document de
    vérification (stockage privé) ne devient jamais accessible via le
    montage public `/static/avatars`, même en devinant sa clé de stockage
    réelle (récupérée ici directement en base, un tiers ne l'aurait pas)."""
    settings = get_settings().model_copy(update={"storage_local_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings

    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)

    async with await _client() as client:
        upload = await client.post(
            "/api/v1/artisans/me/documents",
            headers={"Authorization": f"Bearer {token}"},
            data={"doc_type": "cni"},
            files={"file": ("cni.png", _PNG_BYTES, "image/png")},
        )
        assert upload.status_code == 201

        stmt = select(Verification.doc_url).order_by(Verification.created_at.desc()).limit(1)
        doc_key = (await db_session.execute(stmt)).scalar_one()

        # Le fichier privé vit sous un répertoire (tmp_path) totalement
        # distinct de celui monté publiquement (`avatar_storage_local_dir`,
        # fixé par app.main au démarrage) -- une tentative directe sur le
        # montage public, avec la vraie clé, doit échouer.
        response = await client.get(f"/static/avatars/{doc_key}")

    assert response.status_code == 404
    app.dependency_overrides.pop(get_settings, None)


async def test_generated_media_keys_are_random_not_guessable(db_session: AsyncSession) -> None:
    artisan_user = await make_user(db_session, role=Role.ARTISAN)
    await make_artisan_profile(db_session, user=artisan_user)
    token = encode_access_token(artisan_user)
    settings = get_settings()
    written_files: list[Path] = []

    try:
        async with await _client() as client:
            avatar = await client.post(
                "/api/v1/artisans/me/avatar",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
            )
            cover = await client.post(
                "/api/v1/artisans/me/cover",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cover.png", _PNG_BYTES, "image/png")},
            )

        for url in (avatar.json()["avatar_url"], cover.json()["cover_url"]):
            key = url.rsplit("/static/avatars/", 1)[1]
            written_files.append(resolve_local_dir(settings.avatar_storage_local_dir) / key)
            filename = key.rsplit("/", 1)[-1]
            match = _RANDOM_KEY_RE.search(filename)
            assert match, filename
            # Un `uuid4` réel, pas juste "32 caractères hexa par hasard" --
            # lève ValueError sinon (garde contre une regex trop permissive).
            uuid.UUID(match.group(1))
    finally:
        for path in written_files:
            path.unlink(missing_ok=True)
