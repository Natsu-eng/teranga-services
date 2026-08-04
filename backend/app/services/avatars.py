"""Upload de la photo de profil artisan (BUILD_PLAN.md, onboarding artisan).

Contrairement aux documents de vérification (`app.services.documents`,
strictement privés), un avatar est une donnée PUBLIQUE : affiché en
recherche et sur le profil détaillé (`app.services.artisans`). Stocké via
`app.services.storage.get_avatar_storage_backend` (répertoire dédié, monté
en lecture publique par `app.main`), jamais mélangé avec le stockage privé.
"""

import contextlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.user import User
from app.schemas.artisans import ArtisanDetailOut
from app.services.artisans import get_own_profile, to_detail
from app.services.file_validation import EXTENSION_BY_TYPE, DetectedFileType, detect_file_type
from app.services.storage import StorageBackend

# Une photo de profil est une image, jamais un PDF (contrairement à un
# document de vérification qui peut être un scan).
ALLOWED_AVATAR_TYPES = frozenset({DetectedFileType.JPEG, DetectedFileType.PNG})


class AvatarVideError(AppError):
    def __init__(self) -> None:
        super().__init__(code="AVATAR_VIDE", message="Le fichier envoyé est vide.", status_code=422)


class AvatarTypeInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AVATAR_TYPE_INVALIDE",
            message="La photo de profil doit être une image JPEG ou PNG (vérifié par son "
            "contenu, pas par son nom).",
            status_code=422,
        )


class AvatarTropVolumineuxError(AppError):
    def __init__(self, max_bytes: int) -> None:
        max_mo = max_bytes // (1024 * 1024)
        super().__init__(
            code="AVATAR_TROP_VOLUMINEUX",
            message=f"La photo dépasse la taille maximale autorisée ({max_mo} Mo).",
            status_code=413,
        )


def _avatar_key_from_url(avatar_url: str, *, settings: Settings) -> str | None:
    """Reconstruit la clé de stockage depuis une `avatar_url` déjà générée
    par ce service -- `None` si l'URL ne vient pas d'ici (avatar hérité
    d'avant ce lot, ou jamais défini), auquel cas on ne tente aucune
    suppression (jamais assez confiant pour effacer un fichier qu'on n'a
    pas soi-même écrit)."""
    prefix = f"{settings.backend_public_base_url}/static/avatars/"
    if not avatar_url.startswith(prefix):
        return None
    return avatar_url.removeprefix(prefix)


async def upload_avatar(
    session: AsyncSession,
    *,
    user: User,
    content: bytes,
    settings: Settings,
    storage: StorageBackend,
) -> ArtisanDetailOut:
    if not content:
        raise AvatarVideError()
    if len(content) > settings.avatar_max_upload_bytes:
        raise AvatarTropVolumineuxError(settings.avatar_max_upload_bytes)

    detected = detect_file_type(content)
    if detected is None or detected not in ALLOWED_AVATAR_TYPES:
        raise AvatarTypeInvalideError()

    profile = await get_own_profile(session, user)

    extension = EXTENSION_BY_TYPE[detected]
    key = f"{profile.id}/{uuid.uuid4().hex}.{extension}"
    reference = await storage.store(content, key)

    # Best-effort : supprime l'ancien fichier s'il vient bien de ce service
    # (jamais bloquant -- un avatar orphelin sur disque n'est jamais pire
    # qu'un échec de mise à jour du profil).
    if profile.avatar_url:
        old_key = _avatar_key_from_url(profile.avatar_url, settings=settings)
        if old_key is not None:
            with contextlib.suppress(OSError, ValueError):
                await storage.delete(old_key)

    profile.avatar_url = f"{settings.backend_public_base_url}/static/avatars/{reference}"
    await session.flush()

    required_doc_types = list(settings.verification_required_doc_types)
    return to_detail(profile, required_doc_types=required_doc_types)
