"""Logique métier de la messagerie in-app client ↔ artisan (BUILD_PLAN.md §3.2,
Messagerie).

Principes (documentés dans BUILD_PLAN.md) :

1. **Rattachée à un engagement réel.** Une conversation naît avec son
   intervention, dans la même transaction (`create_for_intervention`,
   appelée par `app.services.interventions.create_intervention`). Jamais de
   canal libre avant engagement : c'est ce qui empêche la messagerie de
   devenir une porte de sortie de la plateforme.
2. **Deux participants, personne d'autre.** Le client et l'artisan de
   l'intervention. Tout autre compte (y compris un admin dans ce lot) reçoit
   la MÊME erreur qu'une conversation inexistante (403
   CONVERSATION_ACCES_INTERDIT) : aucune différence observable ne révèle
   l'existence d'un fil.
3. **L'écriture passe toujours par REST.** Le message est validé, masqué
   (`app.services.contact_masking`) puis persisté AVANT toute diffusion
   WebSocket : un message accepté est un message enregistré, même si aucun
   WebSocket n'est ouvert. Le temps réel ne fait que notifier.
4. **Aucune coordonnée ne fuit** : texte masqué à l'envoi, interlocuteur
   présenté par son seul nom public, images réencodées (EXIF/GPS retirés)
   et servies uniquement aux participants.
"""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import InterventionStatus, Role
from app.models.intervention import Intervention
from app.models.messaging import Conversation, Message
from app.models.user import User
from app.repositories import conversations as conversations_repository
from app.schemas.conversations import (
    ConversationOut,
    ConversationSummaryOut,
    LastMessagePreviewOut,
    MessageHistoryOut,
    MessageOut,
    ParticipantOut,
)
from app.schemas.pagination import Page
from app.services.artisans import PageHorsBornesError
from app.services.contact_masking import mask_contacts
from app.services.file_validation import (
    EXTENSION_BY_TYPE,
    MIME_BY_TYPE,
    DetectedFileType,
    detect_file_type,
)
from app.services.identity import public_display_name
from app.services.image_processing import (
    ImageNonDecodableError,
    ImageTropGrandeError,
    reencode_image,
)
from app.services.storage import StorageBackend, StorageObjectIntrouvableError

# Seules des photos sont acceptées dans le fil (jamais un PDF ni un autre
# format) : elles sont réencodées, donc on sait exactement ce qu'on sert.
_ALLOWED_ATTACHMENT_TYPES = frozenset({DetectedFileType.JPEG, DetectedFileType.PNG})

# Aperçu du dernier message dans la liste : tronqué, la conversation
# complète se lit dans le fil.
_PREVIEW_MAX_CHARS = 120


class ConversationAccesInterditError(AppError):
    """Même réponse pour « n'existe pas » et « pas participant » : rien ne
    permet à un tiers de deviner qu'un fil existe."""

    def __init__(self) -> None:
        super().__init__(
            code="CONVERSATION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette conversation.",
            status_code=403,
        )


class ConversationFermeeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CONVERSATION_FERMEE",
            message=(
                "Cette mise en relation a été refusée : la conversation n'accepte plus "
                "de nouveaux messages."
            ),
            status_code=409,
        )


class MessageVideError(AppError):
    def __init__(self) -> None:
        super().__init__(code="MESSAGE_VIDE", message="Le message est vide.", status_code=422)


class MessageTropLongError(AppError):
    def __init__(self, max_length: int) -> None:
        super().__init__(
            code="MESSAGE_TROP_LONG",
            message=f"Le message dépasse la longueur maximale ({max_length} caractères).",
            status_code=422,
        )


class CurseursIncompatiblesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CURSEURS_INCOMPATIBLES",
            message="Les paramètres « before » et « since » ne peuvent pas être combinés.",
            status_code=422,
        )


class PieceJointeVideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_VIDE", message="Le fichier envoyé est vide.", status_code=422
        )


class PieceJointeTypeInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_TYPE_INVALIDE",
            message="Seules les photos JPEG ou PNG peuvent être envoyées (vérifié par leur "
            "contenu, pas par leur nom).",
            status_code=422,
        )


class PieceJointeTropVolumineuseError(AppError):
    def __init__(self, max_bytes: int) -> None:
        max_mo = max_bytes // (1024 * 1024)
        super().__init__(
            code="PIECE_JOINTE_TROP_VOLUMINEUSE",
            message=f"La photo dépasse la taille maximale autorisée ({max_mo} Mo).",
            status_code=413,
        )


class PieceJointeDimensionsExcessivesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_DIMENSIONS_EXCESSIVES",
            message="Les dimensions de cette photo sont trop grandes.",
            status_code=422,
        )


class PieceJointeIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_INTROUVABLE",
            message="Cette pièce jointe est introuvable.",
            status_code=404,
        )


@dataclass(frozen=True)
class SentMessage:
    """Résultat d'un envoi : le message à renvoyer ET à diffuser, ses
    destinataires temps réel (les deux participants), et la clé du fichier
    stocké pour une image (à effacer si le commit échoue ensuite)."""

    message: MessageOut
    recipient_ids: tuple[uuid.UUID, uuid.UUID]
    stored_attachment_key: str | None


# --------------------------------------------------------------- Création


async def create_for_intervention(
    session: AsyncSession, *, intervention: Intervention, artisan_user_id: uuid.UUID
) -> Conversation:
    """Ouvre le fil d'une intervention qui vient d'être créée (même
    transaction : pas d'intervention sans son fil, ni l'inverse)."""
    return await conversations_repository.create(
        session,
        intervention=intervention,
        client_id=intervention.client_id,
        artisan_user_id=artisan_user_id,
    )


# --------------------------------------------------------------- Lecture


def _is_participant(conversation: Conversation, user: User) -> bool:
    return user.id in (conversation.client_id, conversation.artisan_id)


async def get_for_participant(
    session: AsyncSession, *, conversation_id: uuid.UUID, user: User
) -> Conversation:
    conversation = await conversations_repository.get_by_id(session, conversation_id)
    if conversation is None or not _is_participant(conversation, user):
        raise ConversationAccesInterditError()
    return conversation


def _other_party(conversation: Conversation, viewer: User) -> ParticipantOut:
    if viewer.id == conversation.client_id:
        artisan_user = conversation.artisan_user
        profile = artisan_user.artisan_profile
        return ParticipantOut(
            user_id=artisan_user.id,
            role=Role.ARTISAN,
            display_name=public_display_name(artisan_user.full_name),
            avatar_url=profile.avatar_url if profile else None,
            artisan_profile_id=profile.id if profile else None,
        )
    client = conversation.client
    return ParticipantOut(
        user_id=client.id,
        role=Role.CLIENT,
        display_name=public_display_name(client.full_name),
        avatar_url=None,
        artisan_profile_id=None,
    )


def _intervention_status(conversation: Conversation) -> InterventionStatus | None:
    return conversation.intervention.status if conversation.intervention else None


def _trade_label(conversation: Conversation) -> str | None:
    intervention = conversation.intervention
    if intervention is None:
        return None
    return intervention.service_request.trade.label_fr


def _can_send(conversation: Conversation) -> bool:
    # Refusée par l'artisan = aucun engagement : le fil reste lisible mais
    # n'accepte plus de messages (sinon il servirait à négocier hors cadre).
    return _intervention_status(conversation) is not InterventionStatus.ANNULEE


def _my_cursor(conversation: Conversation, user: User) -> int:
    if user.id == conversation.client_id:
        return conversation.client_last_read_seq
    return conversation.artisan_last_read_seq


def to_message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        seq=message.seq,
        sender_id=message.sender_id,
        body=message.body,
        contact_masked=message.contact_masked,
        has_attachment=message.attachment_key is not None,
        attachment_content_type=message.attachment_content_type,
        created_at=message.created_at,
    )


def _preview(message: Message, viewer: User) -> LastMessagePreviewOut:
    body = message.body
    if len(body) > _PREVIEW_MAX_CHARS:
        body = body[: _PREVIEW_MAX_CHARS - 1].rstrip() + "…"
    return LastMessagePreviewOut(
        body=body,
        from_me=message.sender_id == viewer.id,
        has_attachment=message.attachment_key is not None,
        created_at=message.created_at,
    )


async def list_my_conversations(
    session: AsyncSession,
    *,
    user: User,
    page: int,
    page_size: int,
    settings: Settings,
    artisan_profile_id: uuid.UUID | None = None,
) -> Page[ConversationSummaryOut]:
    """Conversations de l'utilisateur, les plus actives d'abord. Trois
    requêtes au total quelle que soit la taille de la page (conversations,
    derniers messages, non-lus)."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    conversations = await conversations_repository.list_for_user(
        session,
        user_id=user.id,
        limit=resolved_page_size,
        offset=offset,
        artisan_profile_id=artisan_profile_id,
    )
    total = await conversations_repository.count_for_user(
        session, user_id=user.id, artisan_profile_id=artisan_profile_id
    )
    ids = [conversation.id for conversation in conversations]
    last_messages = await conversations_repository.last_messages(session, ids)
    unread = await conversations_repository.unread_counts(
        session, conversation_ids=ids, user_id=user.id
    )

    items = [
        ConversationSummaryOut(
            id=conversation.id,
            intervention_id=conversation.intervention_id,
            intervention_status=_intervention_status(conversation),
            trade_label=_trade_label(conversation),
            other_party=_other_party(conversation, user),
            last_message=(
                _preview(last_messages[conversation.id], user)
                if conversation.id in last_messages
                else None
            ),
            unread_count=unread.get(conversation.id, 0),
            last_activity_at=conversations_repository.last_activity(conversation),
        )
        for conversation in conversations
    ]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)


async def get_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, user: User
) -> ConversationOut:
    conversation = await get_for_participant(session, conversation_id=conversation_id, user=user)
    return ConversationOut(
        id=conversation.id,
        intervention_id=conversation.intervention_id,
        intervention_status=_intervention_status(conversation),
        trade_label=_trade_label(conversation),
        other_party=_other_party(conversation, user),
        my_last_read_seq=_my_cursor(conversation, user),
        can_send=_can_send(conversation),
        created_at=conversation.created_at,
    )


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user: User,
    settings: Settings,
    before_seq: int | None,
    since_seq: int | None,
    limit: int | None,
) -> MessageHistoryOut:
    """Historique (`before`) ou nouveaux messages (`since`, repli polling)."""
    if before_seq is not None and since_seq is not None:
        raise CurseursIncompatiblesError()
    conversation = await get_for_participant(session, conversation_id=conversation_id, user=user)
    resolved_limit = min(
        limit or settings.messaging_history_page_size_default,
        settings.messaging_history_page_size_max,
    )

    messages = await conversations_repository.list_messages(
        session,
        conversation_id=conversation.id,
        limit=resolved_limit,
        before_seq=before_seq,
        since_seq=since_seq,
    )
    has_more = False
    if since_seq is None and messages:
        has_more = await conversations_repository.has_messages_before(
            session, conversation_id=conversation.id, seq=messages[0].seq
        )
    return MessageHistoryOut(items=[to_message_out(m) for m in messages], has_more=has_more)


async def unread_count(session: AsyncSession, *, user: User) -> int:
    return await conversations_repository.total_unread(session, user_id=user.id)


async def mark_read(
    session: AsyncSession, *, conversation_id: uuid.UUID, user: User, last_read_seq: int
) -> ConversationOut:
    conversation = await get_for_participant(session, conversation_id=conversation_id, user=user)
    await conversations_repository.mark_read(
        session, conversation=conversation, user_id=user.id, seq=last_read_seq
    )
    return await get_conversation(session, conversation_id=conversation_id, user=user)


# --------------------------------------------------------------- Envoi


def _clean_body(raw: str, *, settings: Settings, allow_empty: bool) -> str:
    body = raw.strip()
    if not body and not allow_empty:
        raise MessageVideError()
    if len(body) > settings.messaging_body_max_length:
        raise MessageTropLongError(settings.messaging_body_max_length)
    return body


async def _writable_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, sender: User
) -> Conversation:
    conversation = await get_for_participant(session, conversation_id=conversation_id, user=sender)
    if not _can_send(conversation):
        raise ConversationFermeeError()
    return conversation


async def send_text_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    sender: User,
    body: str,
    settings: Settings,
) -> SentMessage:
    """Valide, MASQUE puis persiste. La diffusion temps réel est faite par
    la route, après le commit."""
    conversation = await _writable_conversation(
        session, conversation_id=conversation_id, sender=sender
    )
    cleaned = _clean_body(body, settings=settings, allow_empty=False)
    masking = mask_contacts(cleaned)
    message = await conversations_repository.add_message(
        session,
        conversation=conversation,
        sender_id=sender.id,
        body=masking.text,
        contact_masked=masking.masked,
    )
    return SentMessage(
        message=to_message_out(message),
        recipient_ids=(conversation.client_id, conversation.artisan_id),
        stored_attachment_key=None,
    )


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
