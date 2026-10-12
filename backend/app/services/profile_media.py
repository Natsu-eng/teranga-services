"""Briques communes aux deux médias PUBLICS du profil artisan (avatar et
couverture, BUILD_PLAN.md lot `feat/profile-media`).

Deux règles de fiabilité y vivent, une seule fois pour les deux médias :

1. **On ne supprime jamais un fichier qu'on ne peut pas prouver être le
   sien.** `avatar_url` et `cover_url` restent éditables à la main via
   `PATCH /artisans/me` (champ « URL d'image existante » de l'onboarding) :
   reconnaître seulement le préfixe `/static/avatars/` permettrait donc à un
   artisan de coller l'URL publique du média d'un AUTRE artisan, puis
   d'uploader une nouvelle photo pour faire effacer le fichier de cet autre
   artisan. `owned_media_key` exige donc une clé exactement au format généré
   par ce lot, rangée sous le répertoire du profil courant et du bon type
   (une couverture ne fait jamais effacer un avatar, et inversement).

2. **L'ancien fichier n'est supprimé qu'APRÈS le commit.** Si on l'effaçait
   avant et que le commit échouait, le profil continuerait de pointer vers
   un fichier disparu (image cassée sur la fiche publique). Le service
   renvoie donc la clé obsolète dans `MediaUploadResult`, et la route
   l'efface une fois la nouvelle URL durablement enregistrée
   (`discard_obsolete_media`). Le cas inverse (commit raté après l'écriture
   du nouveau fichier) laisse au pire un fichier orphelin sur disque, ce qui
   n'est jamais visible par un visiteur.
"""

import asyncio
import contextlib
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.artisans import ArtisanDetailOut, MediaUploadLimitsOut, ProfileMediaConstraintsOut
from app.services.file_validation import EXTENSION_BY_TYPE, MIME_BY_TYPE, DetectedFileType
from app.services.image_processing import ImageTropGrandeError, ProcessedImage, reencode_image
from app.services.storage import S3_PUBLIC_MEDIA_PREFIX, StorageBackend

# Chemin public sous lequel `app.main` monte le stockage des médias de
# profil -- partagé par l'avatar et la couverture (même régime public).
PUBLIC_MEDIA_PATH = "/static/avatars/"

# Un média de profil est toujours une image, jamais un PDF (contrairement à
# un document de vérification, qui peut être un scan).
ALLOWED_MEDIA_TYPES = frozenset({DetectedFileType.JPEG, DetectedFileType.PNG})

_MEDIA_EXTENSIONS = "|".join(sorted(EXTENSION_BY_TYPE[t] for t in ALLOWED_MEDIA_TYPES))


class MediaKind(StrEnum):
    AVATAR = "avatar"
    COVER = "cover"


# Préfixe du nom de fichier par type de média : la couverture est préfixée
# `cover-` (lisibilité du répertoire pour un humain), l'avatar n'a aucun
# préfixe (format historique, conservé pour reconnaître les avatars déjà
# uploadés avant ce lot).
_FILENAME_PREFIX: dict[MediaKind, str] = {MediaKind.AVATAR: "", MediaKind.COVER: "cover-"}


class ImageDimensionsExcessivesError(AppError):
    """Commune aux deux médias : la limite porte sur le décodage, pas sur
    l'usage de l'image."""

    def __init__(self, *, width: int | None, height: int | None, max_pixels: int) -> None:
        max_mpx = max_pixels // 1_000_000
        size = f"{width} × {height} pixels, " if width and height else ""
        super().__init__(
            code="IMAGE_DIMENSIONS_EXCESSIVES",
            message=f"L'image est trop grande ({size}{max_mpx} mégapixels maximum).",
            status_code=422,
        )


def max_side_px(kind: MediaKind, settings: Settings) -> int:
    return settings.avatar_max_side_px if kind is MediaKind.AVATAR else settings.cover_max_side_px


def media_constraints(settings: Settings) -> ProfileMediaConstraintsOut:
    """Contraintes réellement appliquées par `upload_avatar`/`upload_cover`,
    dérivées des mêmes réglages -- elles ne peuvent donc jamais diverger de
    ce que le serveur accepte."""
    return ProfileMediaConstraintsOut(
        accepted_mime_types=sorted(MIME_BY_TYPE[t] for t in ALLOWED_MEDIA_TYPES),
        max_pixels=settings.profile_media_max_pixels,
        avatar=MediaUploadLimitsOut(
            max_upload_bytes=settings.avatar_max_upload_bytes,
            max_side_px=settings.avatar_max_side_px,
        ),
        cover=MediaUploadLimitsOut(
            max_upload_bytes=settings.cover_max_upload_bytes,
            max_side_px=settings.cover_max_side_px,
        ),
    )


async def prepare_profile_image(
    content: bytes, *, kind: MediaKind, settings: Settings
) -> ProcessedImage:
    """Réencode l'image envoyée (app/services/image_processing.py) hors de
    la boucle d'événements. Laisse remonter `ImageNonDecodableError`, que
    chaque service traduit dans SON message d'erreur (avatar/couverture)."""
    try:
        return await asyncio.to_thread(
            reencode_image,
            content,
            max_side_px=max_side_px(kind, settings),
            max_pixels=settings.profile_media_max_pixels,
        )
    except ImageTropGrandeError as exc:
        raise ImageDimensionsExcessivesError(
            width=exc.width, height=exc.height, max_pixels=exc.max_pixels
        ) from None


@dataclass(frozen=True)
class MediaUploadResult:
    """Résultat d'un upload de média : le profil à renvoyer au client, et la
    clé de l'ancien fichier à effacer APRÈS le commit (`None` s'il n'y a
    rien à effacer, ou rien qu'on puisse prouver être à nous)."""

    detail: ArtisanDetailOut
    obsolete_key: str | None


def build_media_key(*, profile_id: uuid.UUID, kind: MediaKind, detected: DetectedFileType) -> str:
    """Clé de stockage d'un nouveau média : aléatoire (`uuid4().hex`, jamais
    devinable par un tiers), rangée sous le répertoire du profil."""
    extension = EXTENSION_BY_TYPE[detected]
    return f"{profile_id}/{_FILENAME_PREFIX[kind]}{uuid.uuid4().hex}.{extension}"


def public_media_base(settings: Settings) -> str:
    """Préfixe de toute URL publique de média : le backend en local
    (`/static/avatars/`), le bucket public en S3 (`S3_PUBLIC_BASE_URL`)."""
    if settings.avatar_storage_backend == "s3" and settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{S3_PUBLIC_MEDIA_PREFIX}/"
    return f"{settings.backend_public_base_url}{PUBLIC_MEDIA_PATH}"


def public_media_url(reference: str, *, settings: Settings) -> str:
    """URL ABSOLUE du média (front et back sont sur deux origines distinctes,
    voir `BACKEND_PUBLIC_BASE_URL`)."""
    return f"{public_media_base(settings)}{reference}"


def owned_media_key(
    url: str | None, *, settings: Settings, profile_id: uuid.UUID, kind: MediaKind
) -> str | None:
    """Clé de stockage de `url` SEULEMENT si elle désigne un fichier généré
    par ce lot, pour CE profil et CE type de média -- `None` sinon (URL
    externe collée à la main, média hérité, média d'un autre artisan, ou
    média de l'autre type). Voir la règle 1 du docstring du module."""
    if not url:
        return None
    prefix = public_media_base(settings)
    if not url.startswith(prefix):
        return None
    key = url.removeprefix(prefix)
    # Format exact généré par `build_media_key` : aucune place pour un `..`,
    # un autre répertoire de profil ou un préfixe de l'autre type de média.
    directory = re.escape(str(profile_id))
    filename = rf"{_FILENAME_PREFIX[kind]}[0-9a-f]{{32}}\.(?:{_MEDIA_EXTENSIONS})"
    if re.fullmatch(f"{directory}/{filename}", key) is None:
        return None
    return key


async def discard_obsolete_media(storage: StorageBackend, key: str | None) -> None:
    """Efface l'ancien média, en best-effort : appelé après le commit, un
    échec ici ne laisse qu'un fichier orphelin sur disque -- jamais pire
    qu'un échec de la mise à jour du profil elle-même."""
    if key is None:
        return
    with contextlib.suppress(OSError, ValueError):
        await storage.delete(key)
