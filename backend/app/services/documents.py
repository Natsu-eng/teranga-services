"""Logique métier des documents de vérification artisan (BUILD_PLAN.md,
onboarding artisan). Upload, listing des métadonnées (jamais le binaire) et
lecture du contenu (propriétaire uniquement) -- toujours via la couche de
stockage abstraite (`app.services.storage`), jamais un accès disque direct
ni une URL publique.

Sécurité (non négociable, voir BUILD_PLAN.md) :
- le type réel du fichier est vérifié par magic bytes
  (`app.services.file_validation`), jamais par l'extension ni le
  `Content-Type` déclaré par le client ;
- la clé de stockage est un identifiant aléatoire (`uuid4`), jamais le nom
  de fichier fourni par le client ;
- `verification.doc_url` est une référence de stockage interne, jamais une
  URL publique ni devinable.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.artisan import ArtisanProfile, Verification
from app.models.enums import VerificationDocType
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import verification as verification_repository
from app.schemas.artisans import MyVerificationOut, VerificationDocumentOut
from app.services.artisan_errors import ArtisanProfilIntrouvableError
from app.services.artisans import get_artisan_or_404
from app.services.file_validation import EXTENSION_BY_TYPE, DetectedFileType, detect_file_type
from app.services.storage import StorageBackend, StorageObjectIntrouvableError
from app.services.verification import compute_verified_status

# Types de fichiers acceptés par type de document. Un selfie ne peut jamais
# être un PDF (ça n'a pas de sens : c'est une photo) -- les autres documents
# tolèrent aussi bien une photo qu'un scan PDF.
ALLOWED_FILE_TYPES_BY_DOC_TYPE: dict[VerificationDocType, frozenset[DetectedFileType]] = {
    VerificationDocType.CNI: frozenset(
        {DetectedFileType.JPEG, DetectedFileType.PNG, DetectedFileType.PDF}
    ),
    VerificationDocType.SELFIE: frozenset({DetectedFileType.JPEG, DetectedFileType.PNG}),
    VerificationDocType.ACCREDITATION: frozenset(
        {DetectedFileType.JPEG, DetectedFileType.PNG, DetectedFileType.PDF}
    ),
    VerificationDocType.ADDRESS_PROOF: frozenset(
        {DetectedFileType.JPEG, DetectedFileType.PNG, DetectedFileType.PDF}
    ),
}


class FichierVideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="FICHIER_VIDE", message="Le fichier envoyé est vide.", status_code=422
        )


class FichierTypeInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="FICHIER_TYPE_INVALIDE",
            message="Le fichier fourni n'est pas d'un type accepté pour ce document "
            "(vérifié par son contenu, pas par son nom).",
            status_code=422,
        )


class FichierTropVolumineuxError(AppError):
    def __init__(self, max_bytes: int) -> None:
        max_mo = max_bytes // (1024 * 1024)
        super().__init__(
            code="FICHIER_TROP_VOLUMINEUX",
            message=f"Le fichier dépasse la taille maximale autorisée ({max_mo} Mo).",
            status_code=413,
        )


class DocumentIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DOCUMENT_NOT_FOUND", message="Document introuvable.", status_code=404
        )


async def _get_own_profile(session: AsyncSession, user: User) -> ArtisanProfile:
    artisan_id = await artisans_repository.get_artisan_profile_id_by_user_id(session, user.id)
    if artisan_id is None:
        raise ArtisanProfilIntrouvableError()
    return await get_artisan_or_404(session, artisan_id)


def _to_document_out(verification: Verification) -> VerificationDocumentOut:
    return VerificationDocumentOut.model_validate(verification)


async def upload_document(
    session: AsyncSession,
    *,
    user: User,
    doc_type: VerificationDocType,
    content: bytes,
    settings: Settings,
    storage: StorageBackend,
) -> VerificationDocumentOut:
    if not content:
        raise FichierVideError()
    if len(content) > settings.storage_max_upload_bytes:
        raise FichierTropVolumineuxError(settings.storage_max_upload_bytes)

    detected = detect_file_type(content)
    allowed = ALLOWED_FILE_TYPES_BY_DOC_TYPE.get(doc_type, frozenset())
    if detected is None or detected not in allowed:
        raise FichierTypeInvalideError()

    profile = await _get_own_profile(session, user)

    extension = EXTENSION_BY_TYPE[detected]
    # Identifiant aléatoire, jamais le nom de fichier d'origine (non
    # devinable, ne fuite aucune information sur le contenu ou son auteur).
    key = f"{profile.id}/{doc_type.value}/{uuid.uuid4().hex}.{extension}"
    reference = await storage.store(content, key)

    verification = await verification_repository.create_verification(
        session, artisan=profile, doc_type=doc_type, doc_url=reference
    )

    # `verified_status` n'est jamais lu tel quel par la couche de lecture
    # (toujours recalculé à la volée, app.services.verification) mais reste
    # tenue à jour à l'écriture pour ne jamais diverger inutilement
    # (BUILD_PLAN.md §2.2) -- notamment pour rester la source fiable utilisée
    # comme filtre SQL par la recherche publique (app.repositories.artisans).
    required = list(settings.verification_required_doc_types)
    profile.verified_status = compute_verified_status(profile.verifications, required)
    await session.flush()

    return _to_document_out(verification)


async def list_my_documents(
    session: AsyncSession, *, user: User, settings: Settings
) -> MyVerificationOut:
    profile = await _get_own_profile(session, user)
    required = list(settings.verification_required_doc_types)
    verified_status = compute_verified_status(profile.verifications, required)
    documents = sorted(profile.verifications, key=lambda v: v.created_at, reverse=True)
    return MyVerificationOut(
        verified_status=verified_status,
        documents=[_to_document_out(v) for v in documents],
    )


async def get_document_content(
    session: AsyncSession, *, user: User, document_id: uuid.UUID, storage: StorageBackend
) -> tuple[bytes, DetectedFileType]:
    profile = await _get_own_profile(session, user)
    verification = await verification_repository.get_owned(
        session, verification_id=document_id, artisan_id=profile.id
    )
    if verification is None:
        raise DocumentIntrouvableError()

    try:
        content = await storage.retrieve(verification.doc_url)
    except StorageObjectIntrouvableError as exc:
        raise DocumentIntrouvableError() from exc

    detected = detect_file_type(content)
    if detected is None:
        # Ne devrait jamais arriver (le contenu a été validé à l'upload) --
        # filet de sécurité plutôt qu'une 500 non normalisée.
        raise DocumentIntrouvableError()
    return content, detected
