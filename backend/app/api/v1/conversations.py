"""Messagerie in-app : routes REST (BUILD_PLAN.md §3.2, Messagerie).

REST est la SOURCE DE VÉRITÉ : tout envoi passe par ici (validé, masqué,
persisté), et l'historique se relit ici — y compris en repli quand le temps
réel est indisponible (`GET .../messages?since=<seq>`). Le WebSocket
(app/api/v1/realtime.py) ne fait que notifier, APRÈS le commit -- de même
que la notification push du destinataire (tâche d'arrière-plan, après la
réponse : app/services/message_notifications.py).

Réservé aux comptes client et artisan (admin exclu de ce lot), et dans
chaque conversation aux deux seuls participants.
"""

import contextlib
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import SessionFactory, get_session, get_session_factory
from app.models.enums import Role
from app.models.user import User
from app.schemas.conversations import (
    ConversationOut,
    ConversationSummaryOut,
    MarkReadIn,
    MessageCreateIn,
    MessageHistoryOut,
    MessageOut,
    UnreadCountOut,
)
from app.schemas.pagination import Page
from app.services import conversation_attachments as conversation_attachments_service
from app.services import conversations as conversations_service
from app.services.conversations import SentMessage
from app.services.message_notifications import notify_new_message
from app.services.rate_limit import (
    RateLimiter,
    get_message_attachment_rate_limiter,
    get_message_send_rate_limiter,
)
from app.services.realtime import (
    conversation_read_event,
    message_created_event,
    realtime_bus,
)
from app.services.storage import (
    StockageIndisponibleError,
    get_message_attachment_storage_backend,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

Participant = Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]


class TropDeMessagesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Vous envoyez des messages trop rapidement. Patientez un instant.",
            status_code=429,
        )


async def _enforce_budget(
    limiter: RateLimiter, *, user: User, max_hits: int, window_seconds: int
) -> None:
    # Vérifié AVANT toute validation ou écriture : au-delà de la limite, plus
    # rien n'est persisté ni stocké.
    if not await limiter.check(f"user:{user.id}", max_hits=max_hits, window_seconds=window_seconds):
        raise TropDeMessagesError()


async def _deliver(
    sent: SentMessage,
    *,
    sender: User,
    settings: Settings,
    session_factory: SessionFactory,
    background_tasks: BackgroundTasks,
) -> None:
    """Après le commit SEULEMENT : diffusion temps réel aux deux participants,
    puis notification push programmée pour le destinataire (jamais
    l'expéditeur), exécutée après l'envoi de la réponse -- best-effort, elle
    ne peut ni retarder ni faire échouer l'envoi."""
    await realtime_bus().publish(
        sent.recipient_ids, message_created_event(sent.message.model_dump(mode="json"))
    )
    for recipient_id in sent.recipient_ids:
        if recipient_id != sender.id:
            background_tasks.add_task(
                notify_new_message,
                recipient_id,
                sent.message.conversation_id,
                settings,
                session_factory,
            )


@router.get("/me", response_model=Page[ConversationSummaryOut])
async def list_my_conversations(
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
    artisan_id: Annotated[
        uuid.UUID | None,
        Query(description="Profil artisan : seulement les fils avec cet artisan"),
    ] = None,
) -> Page[ConversationSummaryOut]:
    return await conversations_service.list_my_conversations(
        session,
        user=user,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
        artisan_profile_id=artisan_id,
    )


@router.get("/me/unread-count", response_model=UnreadCountOut)
async def get_my_unread_count(session: SessionDep, user: Participant) -> UnreadCountOut:
    return UnreadCountOut(count=await conversations_service.unread_count(session, user=user))


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: Participant
) -> ConversationOut:
    return await conversations_service.get_conversation(
        session, conversation_id=conversation_id, user=user
    )


@router.get("/{conversation_id}/messages", response_model=MessageHistoryOut)
async def list_messages(
    conversation_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    before: Annotated[int | None, Query(ge=1, description="Messages antérieurs à ce seq")] = None,
    since: Annotated[
        int | None, Query(ge=0, description="Messages postérieurs à ce seq (nouveaux)")
    ] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> MessageHistoryOut:
    return await conversations_service.list_messages(
        session,
        conversation_id=conversation_id,
        user=user,
        settings=settings,
        before_seq=before,
        since_seq=since,
        limit=limit,
    )


@router.post(
    "/{conversation_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreateIn,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    limiter: Annotated[RateLimiter, Depends(get_message_send_rate_limiter)],
    session_factory: SessionFactoryDep,
    background_tasks: BackgroundTasks,
) -> MessageOut:
    await _enforce_budget(
        limiter,
        user=user,
        max_hits=settings.rate_limit_message_send_per_user_max,
        window_seconds=settings.rate_limit_message_send_per_user_window_seconds,
    )
    sent = await conversations_service.send_text_message(
        session, conversation_id=conversation_id, sender=user, body=payload.body, settings=settings
    )
    await session.commit()
    # Seulement maintenant que le message est durablement enregistré.
    await _deliver(
        sent,
        sender=user,
        settings=settings,
        session_factory=session_factory,
        background_tasks=background_tasks,
    )
    return sent.message


@router.post(
    "/{conversation_id}/messages/image",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_image_message(
    conversation_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
    limiter: Annotated[RateLimiter, Depends(get_message_attachment_rate_limiter)],
    session_factory: SessionFactoryDep,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form(max_length=20_000)] = "",
) -> MessageOut:
    await _enforce_budget(
        limiter,
        user=user,
        max_hits=settings.rate_limit_message_attachment_per_user_max,
        window_seconds=settings.rate_limit_message_attachment_per_user_window_seconds,
    )
    # Jamais plus que la limite + 1 octet en mémoire : suffit à détecter un
    # fichier trop lourd sans charger un envoi démesuré.
    content = await file.read(settings.message_attachment_max_upload_bytes + 1)
    storage = get_message_attachment_storage_backend(settings)
    sent = await conversation_attachments_service.send_image_message(
        session,
        conversation_id=conversation_id,
        sender=user,
        content=content,
        caption=caption,
        settings=settings,
        storage=storage,
    )
    try:
        await session.commit()
    except Exception:
        # Jamais de fichier orphelin si l'enregistrement échoue au commit --
        # au mieux : un échec du stockage ici (journalisé) ne doit pas
        # masquer l'erreur d'origine, relancée.
        if sent.stored_attachment_key is not None:
            with contextlib.suppress(StockageIndisponibleError):
                await storage.delete(sent.stored_attachment_key)
        raise
    await _deliver(
        sent,
        sender=user,
        settings=settings,
        session_factory=session_factory,
        background_tasks=background_tasks,
    )
    return sent.message


@router.get("/{conversation_id}/messages/{message_id}/attachment")
async def get_message_attachment(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    user: Participant,
) -> Response:
    content, content_type = await conversation_attachments_service.read_attachment(
        session,
        conversation_id=conversation_id,
        message_id=message_id,
        user=user,
        storage=get_message_attachment_storage_backend(settings),
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={
            # Donnée privée : jamais mise en cache par un intermédiaire, ni
            # conservée par le navigateur au-delà de l'affichage.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.post("/{conversation_id}/read", response_model=ConversationOut)
async def mark_conversation_read(
    conversation_id: uuid.UUID, payload: MarkReadIn, session: SessionDep, user: Participant
) -> ConversationOut:
    result = await conversations_service.mark_read(
        session, conversation_id=conversation_id, user=user, last_read_seq=payload.last_read_seq
    )
    await session.commit()
    # Les autres onglets / appareils du lecteur mettent leur badge à jour.
    await realtime_bus().publish(
        (user.id,), conversation_read_event(result.id, result.my_last_read_seq)
    )
    return result
