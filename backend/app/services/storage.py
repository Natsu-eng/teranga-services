"""Stockage de fichiers, derrière une interface indépendante du fournisseur
(BUILD_PLAN.md §onboarding artisan) -- même principe que `app.services.sms`
et `app.services.ai_triage_providers` : le code métier ne connaît que
`StorageBackend`, jamais son implémentation concrète.

Deux fournisseurs, choisis par `STORAGE_BACKEND` (et ses variantes par
usage) :

- `LocalStorageBackend` (dev, défaut) : disque local, hors du dépôt git
  (`backend/var/`, ignoré par `backend/.gitignore`) ; seuls les médias
  publics de profil sont montés en `StaticFiles` (app/main.py) ;
- `S3StorageBackend` (app/services/s3_storage.py, OBLIGATOIRE en
  production : le disque Railway est éphémère) : documents d'identité et
  pièces jointes dans le bucket PRIVÉ, médias de profil dans le bucket
  PUBLIC, deux buckets distincts.

Le code appelant (`app.services.documents`, avatars, messagerie) ne connaît
que le contrat `StorageBackend`.

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
from typing import TYPE_CHECKING, Protocol

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.services.s3_storage import S3Client

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
    pas de disque persistant entre déploiements -- ce backend est donc
    REFUSÉ en production (Settings) : STORAGE_BACKEND=s3 y est obligatoire.
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


# Préfixes (« dossiers ») par usage dans les buckets S3.
S3_DOCUMENTS_PREFIX = "verification-documents"
S3_ATTACHMENTS_PREFIX = "message-attachments"
S3_PUBLIC_MEDIA_PREFIX = "profile-media"

_s3_clients: dict[tuple[str | None, str | None, str], "S3Client"] = {}


def get_s3_client(settings: Settings) -> "S3Client":
    """Client boto3 unique par configuration (pool de connexions partagé)."""
    from app.services.s3_storage import build_s3_client

    key = (settings.s3_endpoint_url, settings.s3_access_key_id, settings.s3_region)
    if key not in _s3_clients:
        _s3_clients[key] = build_s3_client(settings)
    return _s3_clients[key]


def _unknown_backend(name: str, value: object) -> ValueError:
    # Jamais de repli silencieux sur le disque local : une valeur inconnue
    # (qui aurait contourné la validation de Settings) est une erreur.
    return ValueError(f"{name}={value!r} : fournisseur de stockage inconnu (local ou s3).")


def _s3_backend(settings: Settings, *, prefix: str, public: bool) -> StorageBackend:
    from app.services.s3_storage import S3StorageBackend

    # Le bucket découle de l'USAGE, jamais d'un réglage par appelant : un
    # stockage privé ne peut pas viser le bucket public.
    bucket = settings.s3_public_bucket if public else settings.s3_private_bucket
    if not bucket:  # garanti par Settings.validate_storage ; défense en profondeur
        raise RuntimeError("Bucket S3 non configuré.")
    return S3StorageBackend(get_s3_client(settings), bucket=bucket, prefix=prefix, public=public)


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Stockage PRIVÉ des documents de vérification (CNI, selfie)."""
    settings = settings or get_settings()
    if settings.storage_backend == "s3":
        return _s3_backend(settings, prefix=S3_DOCUMENTS_PREFIX, public=False)
    if settings.storage_backend == "local":
        return LocalStorageBackend(resolve_local_dir(settings.storage_local_dir))
    raise _unknown_backend("STORAGE_BACKEND", settings.storage_backend)


def get_avatar_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Stockage PUBLIC (avatars) -- à ne jamais confondre avec
    `get_storage_backend` (documents de vérification, strictement privé).
    `LocalStorageBackend` y écrit sous `Settings.avatar_storage_local_dir`,
    monté en lecture publique par `app.main` (`StaticFiles`) : contrairement
    aux documents de vérification, une photo de profil est censée être
    visible publiquement (résultats de recherche, profil détaillé)."""
    settings = settings or get_settings()
    if settings.avatar_storage_backend == "s3":
        return _s3_backend(settings, prefix=S3_PUBLIC_MEDIA_PREFIX, public=True)
    if settings.avatar_storage_backend == "local":
        return LocalStorageBackend(resolve_local_dir(settings.avatar_storage_local_dir))
    raise _unknown_backend("AVATAR_STORAGE_BACKEND", settings.avatar_storage_backend)


def get_message_attachment_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Stockage PRIVÉ des images jointes à la messagerie -- même régime que
    les documents de vérification : jamais monté en StaticFiles, lu
    uniquement par l'endpoint authentifié réservé aux deux participants
    (`GET /conversations/{id}/messages/{message_id}/attachment`). Répertoire
    distinct (`Settings.message_attachment_storage_local_dir`) pour qu'une
    erreur de configuration d'un stockage n'expose jamais l'autre."""
    settings = settings or get_settings()
    if settings.message_attachment_storage_backend == "s3":
        return _s3_backend(settings, prefix=S3_ATTACHMENTS_PREFIX, public=False)
    if settings.message_attachment_storage_backend == "local":
        return LocalStorageBackend(resolve_local_dir(settings.message_attachment_storage_local_dir))
    raise _unknown_backend(
        "MESSAGE_ATTACHMENT_STORAGE_BACKEND", settings.message_attachment_storage_backend
    )
