"""Upload de la photo de couverture artisan (BUILD_PLAN.md, lot
`feat/profile-media`).

Même régime que l'avatar (`app.services.avatars`) : donnée PUBLIQUE,
affichée sur la fiche artisan que tout visiteur voit, stockée via
`app.services.storage.get_avatar_storage_backend` -- le même stockage
public que l'avatar (ce qui compte pour la confidentialité, c'est
public/privé, pas avatar/couverture), jamais le stockage privé des
documents de vérification. Clé préfixée `cover-` (contre `{uuid}` seul pour
l'avatar) : le répertoire reste lisible par un humain, et surtout
`owned_media_key` distingue ainsi strictement les deux types de média (une
couverture ne fait jamais effacer un avatar). Aucune des deux clés n'est
jamais devinée par un tiers (`uuid4().hex`).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.user import User
from app.services.artisans import get_own_profile, to_detail
from app.services.file_validation import detect_file_type
from app.services.profile_media import (
    ALLOWED_MEDIA_TYPES,
    MediaKind,
    MediaUploadResult,
    build_media_key,
    owned_media_key,
    public_media_url,
)
from app.services.storage import StorageBackend


class CouvertureVideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COUVERTURE_VIDE", message="Le fichier envoyé est vide.", status_code=422
        )


class CouvertureTypeInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="COUVERTURE_TYPE_INVALIDE",
            message="La photo de couverture doit être une image JPEG ou PNG (vérifié par son "
            "contenu, pas par son nom).",
            status_code=422,
        )


class CouvertureTropVolumineuseError(AppError):
    def __init__(self, max_bytes: int) -> None:
        max_mo = max_bytes // (1024 * 1024)
        super().__init__(
            code="COUVERTURE_TROP_VOLUMINEUSE",
            message=f"La photo de couverture dépasse la taille maximale autorisée ({max_mo} Mo).",
            status_code=413,
        )


async def upload_cover(
    session: AsyncSession,
    *,
    user: User,
    content: bytes,
    settings: Settings,
    storage: StorageBackend,
) -> MediaUploadResult:
    """Enregistre la nouvelle couverture et renvoie la clé de l'ancienne à
    effacer -- même contrat que `app.services.avatars.upload_avatar`
    (suppression faite par la route, après le commit)."""
    if not content:
        raise CouvertureVideError()
    if len(content) > settings.cover_max_upload_bytes:
        raise CouvertureTropVolumineuseError(settings.cover_max_upload_bytes)

    detected = detect_file_type(content)
    if detected is None or detected not in ALLOWED_MEDIA_TYPES:
        raise CouvertureTypeInvalideError()

    profile = await get_own_profile(session, user)

    obsolete_key = owned_media_key(
        profile.cover_url, settings=settings, profile_id=profile.id, kind=MediaKind.COVER
    )

    key = build_media_key(profile_id=profile.id, kind=MediaKind.COVER, detected=detected)
    reference = await storage.store(content, key)

    profile.cover_url = public_media_url(reference, settings=settings)
    await session.flush()

    required_doc_types = list(settings.verification_required_doc_types)
    return MediaUploadResult(
        detail=to_detail(profile, required_doc_types=required_doc_types),
        obsolete_key=obsolete_key,
    )
