"""Upload de la photo de profil artisan (BUILD_PLAN.md, onboarding artisan).

Contrairement aux documents de vérification (`app.services.documents`,
strictement privés), un avatar est une donnée PUBLIQUE : affiché en
recherche et sur le profil détaillé (`app.services.artisans`). Stocké via
`app.services.storage.get_avatar_storage_backend` (répertoire dédié, monté
en lecture publique par `app.main`), jamais mélangé avec le stockage privé.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.user import User
from app.services.artisan_profile import get_own_profile
from app.services.artisans import to_detail
from app.services.file_validation import detect_file_type
from app.services.image_processing import ImageNonDecodableError
from app.services.profile_media import (
    ALLOWED_MEDIA_TYPES,
    MediaKind,
    MediaUploadResult,
    build_media_key,
    owned_media_key,
    prepare_profile_image,
    public_media_url,
)
from app.services.storage import StorageBackend


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


async def upload_avatar(
    session: AsyncSession,
    *,
    user: User,
    content: bytes,
    settings: Settings,
    storage: StorageBackend,
) -> MediaUploadResult:
    """Enregistre le nouvel avatar et renvoie la clé de l'ancien à effacer.

    N'efface RIEN lui-même : l'ancien fichier n'est supprimé par la route
    qu'après le commit (voir `app.services.profile_media`, règle 2)."""
    if not content:
        raise AvatarVideError()
    if len(content) > settings.avatar_max_upload_bytes:
        raise AvatarTropVolumineuxError(settings.avatar_max_upload_bytes)

    detected = detect_file_type(content)
    if detected is None or detected not in ALLOWED_MEDIA_TYPES:
        raise AvatarTypeInvalideError()

    profile = await get_own_profile(session, user)

    # Calculée AVANT d'écraser `avatar_url` : seule une URL qu'on peut
    # prouver être la nôtre (ce profil, ce type de média) sera effacée.
    obsolete_key = owned_media_key(
        profile.avatar_url, settings=settings, profile_id=profile.id, kind=MediaKind.AVATAR
    )

    # Jamais les octets envoyés : uniquement l'image décodée puis réencodée
    # (métadonnées EXIF/GPS retirées, redimensionnée) -- voir
    # app/services/image_processing.py.
    try:
        processed = await prepare_profile_image(content, kind=MediaKind.AVATAR, settings=settings)
    except ImageNonDecodableError:
        raise AvatarTypeInvalideError() from None

    key = build_media_key(profile_id=profile.id, kind=MediaKind.AVATAR, detected=processed.detected)
    reference = await storage.store(processed.content, key)

    profile.avatar_url = public_media_url(reference, settings=settings)
    await session.flush()

    required_doc_types = list(settings.verification_required_doc_types)
    return MediaUploadResult(
        detail=to_detail(profile, required_doc_types=required_doc_types),
        obsolete_key=obsolete_key,
    )
