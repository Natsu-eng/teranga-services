"""Stockage de fichiers, derrière une interface indépendante du fournisseur
(BUILD_PLAN.md §onboarding artisan) -- même principe que `app.services.sms`
et `app.services.ai_triage_providers` : le code métier ne connaît que
`StorageBackend`, jamais son implémentation concrète.

`LocalStorageBackend` est le seul fournisseur implémenté à ce stade (dev) :
il écrit sur disque local, hors du dépôt git (`backend/var/`, ignoré par
`backend/.gitignore`) et jamais servi statiquement (`app.main` ne monte
aucun `StaticFiles` -- tout accès passe par un endpoint authentifié qui lit
via `retrieve()`). **Basculer vers un fournisseur cloud privé en prod**
(ex. S3-compatible avec accès privé, GCS) ne demandera d'écrire qu'une
nouvelle classe implémentant ce même Protocol et de la brancher dans
`get_storage_backend` via `STORAGE_BACKEND=<nom>` -- aucune réécriture du
code appelant (`app.services.documents`).

Le contenu est manipulé en `bytes` (jamais un vrai flux) : les documents
concernés (CNI, selfie) sont de petits fichiers, plafonnés en taille par
`Settings.storage_max_upload_bytes` -- bufferiser en mémoire est un choix
délibéré qui garde `LocalStorageBackend` trivial, sans complexité de
streaming asynchrone pour un cas d'usage borné. `retrieve` est servi en
`StreamingResponse` côté endpoint (app/api/v1/artisans.py), donc le client
HTTP reçoit bien une réponse en flux même si le backend de stockage ne
manipule que des `bytes` en interne.
"""

import asyncio
import logging
from pathlib import Path
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Racine du package backend (backend/), calculée depuis ce fichier
# (backend/app/services/storage.py) -- indépendante du répertoire courant
# d'où le process est lancé, contrairement à un chemin relatif naïf.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class StorageObjectIntrouvableError(Exception):
    def __init__(self, reference: str) -> None:
        super().__init__(f"Objet de stockage introuvable : {reference!r}")
        self.reference = reference


class StorageBackend(Protocol):
    async def store(self, content: bytes, key: str) -> str:
        """Persiste `content` sous une clé suggérée `key`, renvoie une
        référence opaque à stocker en base (`verification.doc_url`) --
        jamais une URL publique, jamais devinable depuis l'extérieur."""
        ...

    async def retrieve(self, reference: str) -> bytes:
        """Relit le contenu depuis une référence renvoyée par `store`.
        Lève `StorageObjectIntrouvableError` si la référence n'existe pas."""
        ...

    async def delete(self, reference: str) -> None:
        """Supprime l'objet -- silencieux si déjà absent (idempotent)."""
        ...


class LocalStorageBackend:
    """Backend de dev : écrit sur disque local, hors du dépôt git et hors
    de tout répertoire servi statiquement (voir docstring du module).

    Le déploiement en production sur Railway (BUILD_PLAN.md §1) ne conserve
    pas de disque persistant entre déploiements -- ce backend n'est donc
    volontairement PAS adapté à la prod en l'état ; c'est un fournisseur
    cloud privé qui doit le remplacer avant la mise en production réelle
    (voir `get_storage_backend`).
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Garde-fou défense en profondeur contre un path traversal (ex.
        # key="../../etc/passwd") -- même si `key` est toujours générée
        # côté serveur (identifiant aléatoire, jamais le nom de fichier
        # fourni par le client, voir app.services.documents), on ne fait
        # jamais confiance aveuglément à une chaîne assemblée dans un chemin
        # de fichier.
        candidate = (self._base_dir / key).resolve()
        if candidate != self._base_dir and self._base_dir not in candidate.parents:
            raise ValueError(f"Clé de stockage invalide (hors répertoire racine) : {key!r}")
        return candidate

    def _write(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def store(self, content: bytes, key: str) -> str:
        path = self._resolve(key)
        await asyncio.to_thread(self._write, path, content)
        return key

    async def retrieve(self, reference: str) -> bytes:
        path = self._resolve(reference)
        if not path.is_file():
            raise StorageObjectIntrouvableError(reference)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, reference: str) -> None:
        path = self._resolve(reference)
        await asyncio.to_thread(path.unlink, True)


def resolve_local_dir(raw: str) -> Path:
    """Résout un chemin de `Settings` relatif au dossier `backend/` (pas au
    répertoire courant du process, qui varie selon comment il est lancé) --
    partagé par le stockage privé (documents de vérification) et le stockage
    public (avatars)."""
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path
    return path


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    settings = settings or get_settings()
    if settings.storage_backend == "local":
        return LocalStorageBackend(resolve_local_dir(settings.storage_local_dir))
    raise NotImplementedError(
        f"Backend de stockage {settings.storage_backend!r} non implémenté. "
        "Choisissez et implémentez un fournisseur cloud privé (voir "
        "app/services/storage.py) avant de l'activer via STORAGE_BACKEND."
    )


def get_avatar_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Stockage PUBLIC (avatars) -- à ne jamais confondre avec
    `get_storage_backend` (documents de vérification, strictement privé).
    `LocalStorageBackend` y écrit sous `Settings.avatar_storage_local_dir`,
    monté en lecture publique par `app.main` (`StaticFiles`) : contrairement
    aux documents de vérification, une photo de profil est censée être
    visible publiquement (résultats de recherche, profil détaillé)."""
    settings = settings or get_settings()
    if settings.avatar_storage_backend == "local":
        return LocalStorageBackend(resolve_local_dir(settings.avatar_storage_local_dir))
    raise NotImplementedError(
        f"Backend de stockage avatar {settings.avatar_storage_backend!r} non implémenté. "
        "Choisissez et implémentez un fournisseur cloud (bucket public, CDN) avant de "
        "l'activer via AVATAR_STORAGE_BACKEND."
    )
