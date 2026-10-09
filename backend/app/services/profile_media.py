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

import contextlib
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings
from app.schemas.artisans import ArtisanDetailOut
from app.services.file_validation import EXTENSION_BY_TYPE, DetectedFileType
from app.services.storage import StorageBackend

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


def public_media_url(reference: str, *, settings: Settings) -> str:
    """URL ABSOLUE du média (front et back sont sur deux origines distinctes,
    voir `BACKEND_PUBLIC_BASE_URL`)."""
    return f"{settings.backend_public_base_url}{PUBLIC_MEDIA_PATH}{reference}"


def owned_media_key(
    url: str | None, *, settings: Settings, profile_id: uuid.UUID, kind: MediaKind
) -> str | None:
    """Clé de stockage de `url` SEULEMENT si elle désigne un fichier généré
    par ce lot, pour CE profil et CE type de média -- `None` sinon (URL
    externe collée à la main, média hérité, média d'un autre artisan, ou
    média de l'autre type). Voir la règle 1 du docstring du module."""
    if not url:
        return None
    prefix = f"{settings.backend_public_base_url}{PUBLIC_MEDIA_PATH}"
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
