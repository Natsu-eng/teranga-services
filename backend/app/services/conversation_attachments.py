"""Photos de la messagerie (BUILD_PLAN.md §3.4) : envoi (validation,
réencodage sans métadonnées, stockage PRIVÉ) et lecture réservée aux deux
participants. Extraites de `app.services.conversations` sans changement de
logique.
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.repositories import conversations as conversations_repository
from app.services.contact_masking import mask_contacts
from app.services.conversation_errors import (
    PieceJointeDimensionsExcessivesError,
    PieceJointeIntrouvableError,
    PieceJointeTropVolumineuseError,
    PieceJointeTypeInvalideError,
    PieceJointeVideError,
)
from app.services.conversations import (
    SentMessage,
    _clean_body,
    _writable_conversation,
    get_for_participant,
    to_message_out,
)
from app.services.file_validation import (
    EXTENSION_BY_TYPE,
    MIME_BY_TYPE,
    DetectedFileType,
    detect_file_type,
)
from app.services.image_processing import (
    ImageNonDecodableError,
    ImageTropGrandeError,
    reencode_image,
)
from app.services.storage import StorageBackend, StorageObjectIntrouvableError

# Seules des photos sont acceptées dans le fil (jamais un PDF ni un autre
# format) : elles sont réencodées, donc on sait exactement ce qu'on sert.
_ALLOWED_ATTACHMENT_TYPES = frozenset({DetectedFileType.JPEG, DetectedFileType.PNG})


async def send_image_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    sender: User,
    content: bytes,
    caption: str,
    settings: Settings,
    storage: StorageBackend,
) -> SentMessage:
    """Image jointe, avec légende facultative (masquée elle aussi).

    Jamais les octets envoyés : l'image est entièrement décodée puis
    réencodée (EXIF et position GPS retirés, redimensionnée) — voir
    app/services/image_processing.py. Stockée en PRIVÉ sous une clé
    aléatoire, jamais le nom du fichier fourni par le client.
    """
    conversation = await _writable_conversation(
        session, conversation_id=conversation_id, sender=sender
    )
    cleaned_caption = _clean_body(caption, settings=settings, allow_empty=True)

    if not content:
        raise PieceJointeVideError()
    if len(content) > settings.message_attachment_max_upload_bytes:
        raise PieceJointeTropVolumineuseError(settings.message_attachment_max_upload_bytes)
    detected = detect_file_type(content)
    if detected is None or detected not in _ALLOWED_ATTACHMENT_TYPES:
        raise PieceJointeTypeInvalideError()

    try:
        processed = await asyncio.to_thread(
            reencode_image,
            content,
            max_side_px=settings.message_attachment_max_side_px,
            max_pixels=settings.message_attachment_max_pixels,
        )
    except ImageNonDecodableError:
        raise PieceJointeTypeInvalideError() from None
    except ImageTropGrandeError:
        raise PieceJointeDimensionsExcessivesError() from None

    key = f"{conversation.id}/{uuid.uuid4().hex}.{EXTENSION_BY_TYPE[processed.detected]}"
    reference = await storage.store(processed.content, key)

    masking = mask_contacts(cleaned_caption)
    try:
        message = await conversations_repository.add_message(
            session,
            conversation=conversation,
            sender_id=sender.id,
            body=masking.text,
            contact_masked=masking.masked,
            attachment_key=reference,
            attachment_content_type=MIME_BY_TYPE[processed.detected],
        )
    except Exception:
        # Jamais de fichier orphelin : si l'écriture en base échoue, l'image
        # déjà stockée est effacée.
        await storage.delete(reference)
        raise

    return SentMessage(
        message=to_message_out(message),
        recipient_ids=(conversation.client_id, conversation.artisan_id),
        stored_attachment_key=reference,
    )


async def read_attachment(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    user: User,
    storage: StorageBackend,
) -> tuple[bytes, str]:
    """Contenu d'une image jointe, réservé aux deux participants."""
    conversation = await get_for_participant(session, conversation_id=conversation_id, user=user)
    message = await conversations_repository.get_message(
        session, conversation_id=conversation.id, message_id=message_id
    )
    if message is None or message.attachment_key is None or not message.attachment_content_type:
        raise PieceJointeIntrouvableError()
    try:
        content = await storage.retrieve(message.attachment_key)
    except StorageObjectIntrouvableError:
        raise PieceJointeIntrouvableError() from None
    return content, message.attachment_content_type
