"""Backend de stockage local (BUILD_PLAN.md, onboarding artisan) : écrit
hors du dépôt git et hors de tout répertoire servi statiquement, jamais un
accès disque direct depuis l'appelant -- voir `app.services.storage`."""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.storage import (
    LocalStorageBackend,
    StorageObjectIntrouvableError,
    get_storage_backend,
)


async def test_store_then_retrieve_roundtrips_content(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    reference = await backend.store(b"contenu binaire de test", "artisan-1/cni/abc123.jpg")

    retrieved = await backend.retrieve(reference)

    assert retrieved == b"contenu binaire de test"


async def test_retrieve_unknown_reference_raises(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)

    with pytest.raises(StorageObjectIntrouvableError):
        await backend.retrieve("jamais-ecrit/inconnu.jpg")


async def test_delete_is_idempotent(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    reference = await backend.store(b"x", "a/b/c.jpg")

    await backend.delete(reference)
    await backend.delete(reference)  # deuxième suppression : pas d'erreur

    with pytest.raises(StorageObjectIntrouvableError):
        await backend.retrieve(reference)


async def test_stored_file_lives_under_base_dir_not_at_arbitrary_path(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    await backend.store(b"x", "artisan-1/cni/abc123.jpg")

    stored_path = tmp_path / "artisan-1" / "cni" / "abc123.jpg"
    assert stored_path.is_file()


def test_path_traversal_key_is_rejected(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)

    with pytest.raises(ValueError):
        backend._resolve("../../outside.jpg")  # noqa: SLF001


def test_get_storage_backend_resolves_relative_dir_outside_cwd() -> None:
    settings = get_settings().model_copy(
        update={"storage_backend": "local", "storage_local_dir": "var/artisan-documents"}
    )

    backend = get_storage_backend(settings)

    assert isinstance(backend, LocalStorageBackend)
    # Résolu relativement au dossier backend/, pas au répertoire courant du
    # process (qui peut être n'importe où selon comment pytest est lancé).
    assert backend._base_dir.name == "artisan-documents"  # noqa: SLF001
    assert backend._base_dir.parent.name == "var"  # noqa: SLF001


def test_get_storage_backend_rejects_unknown_backend() -> None:
    # Jamais de repli silencieux sur le disque local pour une valeur inconnue.
    settings = get_settings().model_copy(update={"storage_backend": "local"})
    object.__setattr__(settings, "storage_backend", "gcs")  # contourne Literal pour le test

    with pytest.raises(ValueError, match="fournisseur de stockage inconnu"):
        get_storage_backend(settings)
