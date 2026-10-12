"""Stockage S3-compatible (AWS S3, Cloudflare R2, MinIO...) derrière le
contrat `StorageBackend` (app/services/storage.py) -- DEPLOYMENT.md.

**Pourquoi c'est obligatoire en production** : le disque d'un service
Railway est ÉPHÉMÈRE. Tout fichier écrit localement (documents d'identité,
photos de profil, pièces jointes) disparaît au prochain déploiement ou
redémarrage. `STORAGE_BACKEND=local` est donc refusé en production.

**Privé / public, garanti par la structure et non par une option** :

- les documents d'identité (CNI, selfie) et les pièces jointes de la
  messagerie vont dans le bucket PRIVÉ (`S3_PRIVATE_BUCKET`), qui n'a
  aucune URL publique : ils ne sortent que par les endpoints authentifiés,
  qui les relisent ici (`retrieve`) ;
- seuls les médias de profil (avatar, couverture) vont dans le bucket
  PUBLIC (`S3_PUBLIC_BUCKET`), servi par `S3_PUBLIC_BASE_URL` ;
- les deux buckets doivent être DIFFÉRENTS (refusé au démarrage sinon) :
  aucune erreur de préfixe ou d'ACL ne peut exposer une CNI ;
- aucun objet n'est jamais écrit avec une ACL publique : l'exposition du
  bucket public se règle côté fournisseur (domaine public R2, politique de
  lecture S3), jamais objet par objet.

boto3 est synchrone : chaque appel part dans un thread (`asyncio.to_thread`),
la boucle asynchrone n'est jamais bloquée. Les délais et le nombre de
tentatives sont bornés (`build_s3_client`).
"""

import asyncio
import mimetypes
from typing import TYPE_CHECKING, Any, Protocol, cast

from app.services.storage import StorageObjectIntrouvableError

if TYPE_CHECKING:
    from app.core.config import Settings

# Médias publics : clés aléatoires jamais réutilisées -> cache navigateur et
# CDN d'un an. Contenus privés : jamais mis en cache par un intermédiaire.
PUBLIC_CACHE_CONTROL = "public, max-age=31536000, immutable"
PRIVATE_CACHE_CONTROL = "private, no-store"


class S3Client(Protocol):
    """Sous-ensemble du client boto3 utilisé ici (permet un faux client en test)."""

    def put_object(self, **kwargs: Any) -> Any: ...

    def get_object(self, **kwargs: Any) -> Any: ...

    def delete_object(self, **kwargs: Any) -> Any: ...


def _is_missing(exc: Exception) -> bool:
    """Objet absent, quelle que soit la forme de l'erreur du fournisseur."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", ""))
        return code in ("NoSuchKey", "404", "NotFound")
    return type(exc).__name__ == "NoSuchKey"


class S3StorageBackend:
    """Un bucket et un préfixe (« dossier ») par usage."""

    def __init__(self, client: S3Client, *, bucket: str, prefix: str, public: bool) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/") + "/"
        self._cache_control = PUBLIC_CACHE_CONTROL if public else PRIVATE_CACHE_CONTROL

    def _object_key(self, key: str) -> str:
        # Même garde-fou que le stockage local : la clé est générée côté
        # serveur, mais on refuse toute forme qui sortirait du préfixe.
        parts = key.split("/")
        if not key or key.startswith("/") or any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"Clé de stockage invalide : {key!r}")
        return f"{self._prefix}{key}"

    async def store(self, content: bytes, key: str) -> str:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=self._object_key(key),
            Body=content,
            ContentType=content_type,
            CacheControl=self._cache_control,
        )
        # Même référence opaque qu'en local : la base ne connaît jamais le
        # bucket ni le fournisseur.
        return key

    async def retrieve(self, reference: str) -> bytes:
        object_key = self._object_key(reference)

        def _read() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=object_key)
            except Exception as exc:
                if _is_missing(exc):
                    raise StorageObjectIntrouvableError(reference) from exc
                raise
            body: bytes = response["Body"].read()
            return body

        return await asyncio.to_thread(_read)

    async def delete(self, reference: str) -> None:
        # Idempotent : S3 ne signale pas l'absence d'un objet supprimé.
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=self._object_key(reference)
        )


def build_s3_client(settings: "Settings") -> S3Client:
    """Client boto3 configuré pour un fournisseur S3-compatible."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    # Le client boto3 couvre bien plus que le sous-ensemble utilisé ici.
    return cast(S3Client, client)
